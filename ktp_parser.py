"""Parse teks OCR KTP ke field dan periksa struktur NIK."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

LABELS: dict[str, list[str]] = {
    "nik": [r"NIK"],
    "name": [r"Nama"],
    "birth": [r"Tempat\s*/?\s*Tgl\.?\s*Lahir", r"Tempat\s*/?\s*Tanggal\s*Lahir"],
    "gender": [r"Jenis\s*Kelamin"],
    "blood_type": [r"Gol\.?\s*Darah"],
    "address": [r"Alamat"],
    "rt_rw": [r"RT\s*/\s*RW"],
    "village": [r"Ke[il1|]\s*/\s*Desa", r"Kelurahan\s*/\s*Desa"],
    "district": [r"Kecamatan"],
    "religion": [r"Agama"],
    "marital_status": [r"Status\s*Perkawinan"],
    "occupation": [r"Pekerjaan"],
    "nationality": [r"Kewarganegaraan"],
    "valid_until": [r"Berlaku\s*Hingga"],
}

# huruf yang sering terbaca di posisi angka
DIGIT_FIXES = str.maketrans({"O": "0", "o": "0", "D": "0", "I": "1", "l": "1", "L": "1",
                             "|": "1", "Z": "2", "S": "5", "B": "8", "G": "6"})

PROVINCE_CODES = {
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "21",
    "31", "32", "33", "34", "35", "36", "51", "52", "53",
    "61", "62", "63", "64", "65", "71", "72", "73", "74", "75", "76",
    "81", "82", "91", "92", "93", "94", "95", "96", "97",
}


@dataclass
class KtpResult:
    fields: dict[str, str | None]
    nik_checks: dict[str, bool | None]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "fields": self.fields,
            "nikChecks": self.nik_checks,
            "warnings": self.warnings,
        }


def _clean(value: str) -> str:
    value = re.sub(r"^[\s:;.\-]+", "", value)
    return re.sub(r"\s+", " ", value).strip(" :;-")


CANONICAL_LABELS: dict[str, str] = {
    "nik": "NIK",
    "name": "NAMA",
    "birth": "TEMPATTGLLAHIR",
    "gender": "JENISKELAMIN",
    "blood_type": "GOLDARAH",
    "address": "ALAMAT",
    "rt_rw": "RTRW",
    "village": "KELDESA",
    "district": "KECAMATAN",
    "religion": "AGAMA",
    "marital_status": "STATUSPERKAWINAN",
    "occupation": "PEKERJAAN",
    "nationality": "KEWARGANEGARAAN",
    "valid_until": "BERLAKUHINGGA",
}
LABEL_MIN_SIMILARITY = 0.75
# ambang lebih longgar untuk label yang memang giliran berikutnya
EXPECTED_LABEL_MIN_SIMILARITY = 0.65
LABEL_ORDER = list(CANONICAL_LABELS)


def _letters(text: str) -> str:
    return re.sub(r"[^A-Z]", "", text.upper())


def _match_label(candidate: str, expected: frozenset[str] = frozenset()) -> str | None:
    letters = _letters(candidate)
    if not letters:
        return None
    best_key, best_ratio = None, 0.0
    for key, canonical in CANONICAL_LABELS.items():
        if len(canonical) <= 4 and abs(len(letters) - len(canonical)) > 1:
            continue
        ratio = SequenceMatcher(None, letters, canonical).ratio()
        if ratio > best_ratio:
            best_key, best_ratio = key, ratio
    if best_key is None:
        return None
    minimum = EXPECTED_LABEL_MIN_SIMILARITY if best_key in expected else LABEL_MIN_SIMILARITY
    return best_key if best_ratio >= minimum else None


def _split_line(line: str, expected: frozenset[str] = frozenset()) -> tuple[str | None, str]:
    """'Jente Kelamin : LAKI-LAKI' -> ('gender', 'LAKI-LAKI')"""
    if ":" in line:
        label, _, value = line.partition(":")
        key = _match_label(label, expected)
        if key:
            return key, value
    # tanpa titik dua: ambil awalan 1-3 kata yang paling mirip label
    words = line.split()
    best: tuple[float, str, int] | None = None
    for count in (1, 2, 3):
        if len(words) <= count:
            break
        key = _match_label(" ".join(words[:count]), expected)
        if key:
            ratio = SequenceMatcher(
                None, _letters(" ".join(words[:count])), CANONICAL_LABELS[key]
            ).ratio()
            if best is None or ratio > best[0]:
                best = (ratio, key, count)
    if best:
        return best[1], " ".join(words[best[2]:])
    # label tanpa isi, mis. "RT/RW"
    if len(words) <= 3:
        key = _match_label(line, expected)
        if key:
            return key, ""
    return None, line


def _expected_next(fields: dict[str, str | None], count: int = 3) -> frozenset[str]:
    filled = [i for i, key in enumerate(LABEL_ORDER) if fields.get(key)]
    start = filled[-1] + 1 if filled else 0
    return frozenset([k for k in LABEL_ORDER[start:] if not fields.get(k)][:count])


def _extract_by_lines(text: str) -> dict[str, str | None]:
    fields: dict[str, str | None] = {key: None for key in LABELS}
    previous: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key, value = _split_line(line, _expected_next(fields))
        if key and fields[key] is None:
            fields[key] = _clean(value) or None
            previous = key
        elif key is None and previous and fields[previous] is None:
            fields[previous] = _clean(line) or None
            previous = None
        elif key is None and previous == "address":
            fields["address"] = _clean(f"{fields['address'] or ''} {line}") or None
        elif key is None and previous == "birth" and re.fullmatch(r"[\d\s\-/.]+", line):
            fields["birth"] = _clean(f"{fields['birth'] or ''}, {line}") or None
            previous = None
        elif key is None:
            previous = None
    return fields


def _extract_by_regex(flat: str) -> dict[str, str | None]:
    hits: list[tuple[int, int, str]] = []
    for key, patterns in LABELS.items():
        for pattern in patterns:
            match = re.search(rf"(?<![A-Za-z]){pattern}(?![A-Za-z])", flat, re.IGNORECASE)
            if match:
                hits.append((match.start(), match.end(), key))
                break
    hits.sort()

    fields: dict[str, str | None] = {key: None for key in LABELS}
    for i, (_, end, key) in enumerate(hits):
        stop = hits[i + 1][0] if i + 1 < len(hits) else len(flat)
        fields[key] = _clean(flat[end:stop]) or None
    return fields


def _split_gender_and_blood(fields: dict[str, str | None]) -> None:
    gender = fields.get("gender")
    if not gender:
        return
    match = re.search(r"\bG[o0]l\.?\s*D[a-z]{3,5}\b\s*:?\s*(.*)$", gender, re.IGNORECASE)
    if match:
        fields["gender"] = _clean(gender[: match.start()]) or None
        if not fields.get("blood_type"):
            fields["blood_type"] = _clean(match.group(1)) or None


MIN_BIRTH_YEAR = 1900
GENDER_IN_TEXT = re.compile(r"\b(LAK[I1L]?[\s\-]*LAK[I1]|P[A-Z]{0,4}MPUAN)\b", re.IGNORECASE)
BIRTH_IN_LINE = re.compile(r"[A-Za-z]{3,}\s*[,.]\s*\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{4}\b")


def normalize_gender(value: str | None) -> str | None:
    if not value:
        return None
    letters = _letters(value)
    if "LAK" in letters or "PRIA" in letters:
        return "LAKI-LAKI"
    if "PERE" in letters or "PEREM" in letters or "WANITA" in letters:
        return "PEREMPUAN"
    if SequenceMatcher(None, letters[:9], "PEREMPUAN").ratio() >= 0.7:
        return "PEREMPUAN"
    if SequenceMatcher(None, letters[:8], "LAKILAKI").ratio() >= 0.7:
        return "LAKI-LAKI"
    if "MPUAN" in letters:  # "PHEMPUAN"
        return "PEREMPUAN"
    return None


def extract_fields(text: str) -> dict[str, str | None]:
    flat = re.sub(r"[ \t]+", " ", text.replace("\r", ""))

    fields = _extract_by_lines(text)
    if sum(1 for v in fields.values() if v) < 4:
        fields = _extract_by_regex(flat)
    _split_gender_and_blood(fields)
    fields["gender"] = normalize_gender(fields["gender"])
    if not fields["gender"]:
        match = GENDER_IN_TEXT.search(text)
        fields["gender"] = normalize_gender(match.group(1)) if match else None
    if not split_birth(fields["birth"])[1]:
        # label dan isi bisa terpisah (foto miring)
        for line in text.splitlines():
            if BIRTH_IN_LINE.search(line):
                fields["birth"] = line
                break
    if fields["rt_rw"] and not re.search(r"\d", fields["rt_rw"]):
        fields["rt_rw"] = None

    province = re.search(
        r"PRO[VW]INSI\s*(.+?)(?=\s+(?:KOTA|KABUPATEN)\b|\n|$)", flat, re.IGNORECASE
    )
    regency = re.search(
        r"\b(KOTA|KABUPATEN)[A-Z]?\s+(.+?)(?=\s+NIK\b|\n|$)", flat, re.IGNORECASE
    )
    fields["province"] = _clean(province.group(1)) if province else None
    fields["regency"] = (
        f"{regency.group(1).upper()} {_clean(regency.group(2))}" if regency else None
    )

    fields["nik"] = normalize_nik(fields["nik"]) or next(
        (nik for line in text.splitlines() if (nik := normalize_nik(line))), None
    )
    birth_place, birth_date = split_birth(fields.pop("birth"))
    fields["birth_place"] = birth_place
    fields["birth_date"] = birth_date
    return fields


def normalize_nik(source: str | None) -> str | None:
    if not source:
        return None
    for candidate in re.findall(r"[0-9OoDIlL|ZSBG]{16,}", source):
        digits = candidate.translate(DIGIT_FIXES)
        if re.fullmatch(r"\d{16}", digits):
            return digits
    match = re.search(r"\d{16}", re.sub(r"\s", "", source))
    return match.group(0) if match else None


def split_birth(value: str | None) -> tuple[str | None, str | None]:
    """'BANDUNG, 17-08-2005' -> ('BANDUNG', '2005-08-17')"""
    if not value:
        return None, None
    match = re.search(r"(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4})", value)
    place = _clean(value[: match.start()]) if match else _clean(value)
    place = place.rstrip(",. ") or None
    if not match:
        return place, None
    day, month, year = (int(g) for g in match.groups())
    if not MIN_BIRTH_YEAR <= year <= date.today().year:
        return place, None
    try:
        return place, date(year, month, day).isoformat()
    except ValueError:
        return place, None


def check_nik(nik: str | None, birth_date: str | None, gender: str | None) -> tuple[dict, list[str]]:
    """Cek struktur NIK saja, bukan keterdaftaran di Dukcapil."""
    checks: dict[str, bool | None] = {
        "format": None, "province": None, "birthDate": None, "gender": None, "serial": None,
    }
    warnings: list[str] = []
    if not nik:
        warnings.append("NIK tidak terbaca")
        return checks, warnings

    checks["format"] = bool(re.fullmatch(r"\d{16}", nik))
    if not checks["format"]:
        warnings.append("NIK bukan 16 digit")
        return checks, warnings

    checks["province"] = nik[:2] in PROVINCE_CODES
    if not checks["province"]:
        warnings.append(f"Kode provinsi {nik[:2]} tidak dikenal")

    day, month, year2 = int(nik[6:8]), int(nik[8:10]), int(nik[10:12])
    is_female = day > 40
    real_day = day - 40 if is_female else day

    if birth_date:
        y, m, d = (int(x) for x in birth_date.split("-"))
        checks["birthDate"] = (real_day, month, year2) == (d, m, y % 100)
        if not checks["birthDate"]:
            warnings.append("Tanggal lahir di NIK tidak cocok dengan tanggal lahir di KTP")

    if gender:
        says_female = "PEREMPUAN" in gender.upper()
        says_male = "LAKI" in gender.upper()
        if says_female or says_male:
            checks["gender"] = is_female == says_female
            if not checks["gender"]:
                warnings.append("Jenis kelamin di NIK tidak cocok dengan isian KTP")

    checks["serial"] = nik[12:] != "0000"
    if not checks["serial"]:
        warnings.append("Nomor urut NIK 0000 tidak sah")
    return checks, warnings


def parse_ktp(text: str) -> KtpResult:
    fields = extract_fields(text)
    checks, warnings = check_nik(fields["nik"], fields["birth_date"], fields["gender"])
    missing = [k for k in ("nik", "name", "birth_date", "address") if not fields.get(k)]
    if missing:
        warnings.append("Field penting tidak terbaca: " + ", ".join(missing))
    return KtpResult(fields=fields, nik_checks=checks, warnings=warnings)

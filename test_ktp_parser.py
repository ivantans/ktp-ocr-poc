"""python3 -m unittest -v"""

import unittest

from ktp_parser import check_nik, normalize_nik, parse_ktp

# semua data di sini rekaan
SAMPLE = """PROVINSI JAWA BARAT
KOTA BANDUNG
NIK : 3273015708050003
Nama : SITI AMINAH
Tempat/Tgl Lahir : BANDUNG, 17-08-2005
Jenis Kelamin : PEREMPUAN Gol. Darah : O
Alamat : JL. MERDEKA NO. 1
RT/RW : 001/002
Kel/Desa : SUKAMAJU
Kecamatan : SUKASARI
Agama : ISLAM
Status Perkawinan : BELUM KAWIN
Pekerjaan : PELAJAR/MAHASISWA
Kewarganegaraan : WNI
Berlaku Hingga : SEUMUR HIDUP
"""


class ParseKtpTest(unittest.TestCase):
    def test_semua_field_terbaca(self):
        result = parse_ktp(SAMPLE)
        f = result.fields
        self.assertEqual(f["nik"], "3273015708050003")
        self.assertEqual(f["name"], "SITI AMINAH")
        self.assertEqual(f["birth_place"], "BANDUNG")
        self.assertEqual(f["birth_date"], "2005-08-17")
        self.assertEqual(f["gender"], "PEREMPUAN")
        self.assertEqual(f["blood_type"], "O")
        self.assertEqual(f["address"], "JL. MERDEKA NO. 1")
        self.assertEqual(f["rt_rw"], "001/002")
        self.assertEqual(f["village"], "SUKAMAJU")
        self.assertEqual(f["district"], "SUKASARI")
        self.assertEqual(f["religion"], "ISLAM")
        self.assertEqual(f["marital_status"], "BELUM KAWIN")
        self.assertEqual(f["occupation"], "PELAJAR/MAHASISWA")
        self.assertEqual(f["nationality"], "WNI")
        self.assertEqual(f["province"], "JAWA BARAT")
        self.assertEqual(f["regency"], "KOTA BANDUNG")
        self.assertTrue(all(result.nik_checks.values()))
        self.assertEqual(result.warnings, [])

    def test_titik_dua_hilang_dan_baris_menyatu(self):
        text = SAMPLE.replace(" : ", " ").replace("\n", " ")
        f = parse_ktp(text).fields
        self.assertEqual(f["nik"], "3273015708050003")
        self.assertEqual(f["name"], "SITI AMINAH")
        self.assertEqual(f["district"], "SUKASARI")
        self.assertEqual(f["province"], "JAWA BARAT")
        self.assertEqual(f["regency"], "KOTA BANDUNG")


class LabelOcrTest(unittest.TestCase):
    def test_kel_desa_terbaca_kei(self):
        f = parse_ktp(SAMPLE.replace("Kel/Desa", "Kei/Desa")).fields
        self.assertEqual(f["village"], "SUKAMAJU")

    def test_label_salah_eja_dari_ocr(self):
        text = (
            SAMPLE.replace("Tgl", "Tgi")
            .replace("Kel/Desa", "Ke/Desa")
            .replace("Jenis Kelamin", "Jente Kelamin")
            .replace("Status Perkawinan", "Statun Perkawinan")
            .replace("Kewarganegaraan", "Kewanganegaraan")
            .replace("Berlaku Hingga", "Bertaku Hingga")
            .replace("Nama :", "Name :")
        )
        result = parse_ktp(text)
        f = result.fields
        self.assertEqual(f["birth_date"], "2005-08-17")
        self.assertEqual(f["village"], "SUKAMAJU")
        self.assertEqual(f["gender"], "PEREMPUAN")
        self.assertEqual(f["marital_status"], "BELUM KAWIN")
        self.assertEqual(f["nationality"], "WNI")
        self.assertEqual(f["valid_until"], "SEUMUR HIDUP")
        self.assertEqual(f["name"], "SITI AMINAH")
        self.assertTrue(result.nik_checks["birthDate"] and result.nik_checks["gender"])

    def test_baris_tanpa_titik_dua(self):
        f = parse_ktp(SAMPLE.replace(" : ", " ")).fields
        self.assertEqual(f["name"], "SITI AMINAH")
        self.assertEqual(f["birth_date"], "2005-08-17")
        self.assertEqual(f["occupation"], "PELAJAR/MAHASISWA")

    def test_kelamin_dan_golongan_darah_satu_baris(self):
        text = SAMPLE.replace(
            "Jenis Kelamin : PEREMPUAN Gol. Darah : O",
            "Jenis kelamin : PEREMPUAN : Gol. Darah :",
        )
        f = parse_ktp(text).fields
        self.assertEqual(f["gender"], "PEREMPUAN")
        self.assertIsNone(f["blood_type"])

    def test_tanggal_lahir_di_baris_sendiri(self):
        text = SAMPLE.replace(
            "Tempat/Tgl Lahir : BANDUNG, 17-08-2005", "Tempat/Tgi Lahir : BANDUNG\n17-08-2005"
        )
        f = parse_ktp(text).fields
        self.assertEqual(f["birth_place"], "BANDUNG")
        self.assertEqual(f["birth_date"], "2005-08-17")

    def test_kelamin_tanpa_titik_dua_tidak_menelan_isi(self):
        text = SAMPLE.replace(
            "Jenis Kelamin : PEREMPUAN Gol. Darah : O", "Jenis Kelamin PEREMPUAN Gol. Darah O"
        )
        f = parse_ktp(text).fields
        self.assertEqual(f["gender"], "PEREMPUAN")
        self.assertEqual(f["blood_type"], "O")

    def test_alamat_berlanjut_ke_baris_berikutnya(self):
        text = SAMPLE.replace(
            "Alamat : JL. MERDEKA NO. 1", "Alamat : JL. MERDEKA\nNO. 1"
        )
        self.assertEqual(parse_ktp(text).fields["address"], "JL. MERDEKA NO. 1")

    def test_label_rt_rw_tanpa_isi_tidak_masuk_alamat(self):
        text = SAMPLE.replace(
            "Alamat : JL. MERDEKA NO. 1\nRT/RW : 001/002",
            "Alamat : DUSUN II JL.MELATI\nRT/RW",
        )
        f = parse_ktp(text).fields
        self.assertEqual(f["address"], "DUSUN II JL.MELATI")
        self.assertIsNone(f["rt_rw"])
        self.assertEqual(f["village"], "SUKAMAJU")

    def test_rt_rw_bertanda_strip_dianggap_kosong(self):
        text = SAMPLE.replace("RT/RW : 001/002", "RT/RW : - / -")
        self.assertIsNone(parse_ktp(text).fields["rt_rw"])

    def test_isi_label_di_baris_berikutnya(self):
        text = SAMPLE.replace("Agama : ISLAM", "Agama\nISLAM")
        self.assertEqual(parse_ktp(text).fields["religion"], "ISLAM")

    def test_titik_di_akhir_tempat_lahir_dibuang(self):
        text = SAMPLE.replace("BANDUNG, 17-08-2005", "BANDUNG. 17-08-2005")
        f = parse_ktp(text).fields
        self.assertEqual(f["birth_place"], "BANDUNG")
        self.assertEqual(f["birth_date"], "2005-08-17")


KTP_TTL_RUSAK = """PROVINSIJAWABARAT
KOTA BANDUNG
NIK : 3273011508950001
Nama: BUDI SANTOSO
Tempel/Tgi Lahr: BANDUNG, 15-08-1995
Jenis kelamin: LAKI-LAKI
Alamat: JL-MAWAR-NO2
RT/RW: 000/000
Kel/Desa: SUKAMAJU
Kecamatan: SUKASARI"""

KTP_KELAMIN_RUSAK = """PROVINSI JAWA BARAT
KABUPATENT BANDUNG
NIK : 3204070203860003
Name: AGUS SETIAWAN
Tempat/Tgl Lahr. BANDUNG. 02-03-1986
Jers kanamin LAKI LAKI Gor Darah
Alamat KP MELATI
RT/RW 00000
Kai/Desa CILEUNYI
Kecamatan CILEUNYI WETAN"""


class LabelRusakTest(unittest.TestCase):
    def test_label_tanggal_lahir_rusak_tetap_dikenali_sesuai_urutan(self):
        result = parse_ktp(KTP_TTL_RUSAK)
        f = result.fields
        self.assertEqual(f["birth_place"], "BANDUNG")
        self.assertEqual(f["birth_date"], "1995-08-15")
        self.assertEqual(f["province"], "JAWABARAT")
        self.assertTrue(all(result.nik_checks.values()))

    def test_label_jenis_kelamin_rusak_dan_kabupatent(self):
        result = parse_ktp(KTP_KELAMIN_RUSAK)
        f = result.fields
        self.assertEqual(f["gender"], "LAKI-LAKI")
        self.assertEqual(f["regency"], "KABUPATEN BANDUNG")
        self.assertEqual(f["birth_date"], "1986-03-02")
        self.assertTrue(all(result.nik_checks.values()))

    def test_prowinsi(self):
        text = SAMPLE.replace("PROVINSI JAWA BARAT", "PROWINSI JAWA BARAT")
        self.assertEqual(parse_ktp(text).fields["province"], "JAWA BARAT")

    def test_isi_biasa_tidak_tertangkap_sebagai_label(self):
        text = "NIK : 3273015708050003\nTAPANULI TENGAH\nNama : SITI"
        f = parse_ktp(text).fields
        self.assertEqual(f["name"], "SITI")
        self.assertIsNone(f["address"])


KTP_KOLOM = """PROVINSI JAWA BARAT
KOTA BANDUNG
3273015708050003

NIK
Nama
TempatTgiLahr
Jams kealman
Alamat
SITI AMINAH
BANDUNG, 17-08-2005
PEREMPUAN Col. Darah
JL. MERDEKA NO. 1"""


class TataLetakTest(unittest.TestCase):
    def test_label_dan_isi_terpisah_kolom(self):
        result = parse_ktp(KTP_KOLOM)
        f = result.fields
        self.assertEqual(f["nik"], "3273015708050003")
        self.assertEqual(f["birth_date"], "2005-08-17")
        self.assertEqual(f["gender"], "PEREMPUAN")
        self.assertTrue(all(result.nik_checks.values()))

    def test_label_tanggal_lahir_sendirian_isinya_di_bawah(self):
        text = SAMPLE.replace(
            "Tempat/Tgl Lahir : BANDUNG, 17-08-2005", "Tempat/Tig Lahr\nBANDUNG, 17-08-2005"
        )
        f = parse_ktp(text).fields
        self.assertEqual(f["birth_place"], "BANDUNG")
        self.assertEqual(f["birth_date"], "2005-08-17")

    def test_label_nik_sendirian_tidak_menelan_baris_berikutnya(self):
        text = "PROVINSI JAWA BARAT\n: 3273015708050003\nNIK\nJama\nBANDUNG, 17-08-2005"
        self.assertEqual(parse_ktp(text).fields["nik"], "3273015708050003")

    def test_angka_satu_terbaca_L(self):
        self.assertEqual(normalize_nik("NIK : 327301570805000L"), "3273015708050001")

    def test_tahun_lahir_mustahil_dikosongkan(self):
        text = SAMPLE.replace("3273015708050003", "3273015708650003").replace(
            "17-08-2005", "17-08-1865"
        )
        result = parse_ktp(text)
        self.assertIsNone(result.fields["birth_date"])
        self.assertNotEqual(result.nik_checks["birthDate"], True)

    def test_kelamin_salah_eja_berat(self):
        text = SAMPLE.replace("PEREMPUAN Gol. Darah : O", "PHEMPUAN Gol. Darah : O")
        self.assertEqual(parse_ktp(text).fields["gender"], "PEREMPUAN")


class NikTest(unittest.TestCase):
    def test_huruf_tertukar_angka_diperbaiki(self):
        self.assertEqual(normalize_nik("NIK : 32730I57O8O5OOO3"), "3273015708050003")

    def test_tanggal_dan_kelamin_dari_nik(self):
        # 57 = perempuan, tanggal 17
        checks, warnings = check_nik("3273015708050003", "2005-08-17", "PEREMPUAN")
        self.assertTrue(checks["birthDate"] and checks["gender"])
        self.assertEqual(warnings, [])

    def test_tanggal_lahir_tidak_cocok(self):
        checks, warnings = check_nik("3273011708050003", "2005-08-18", "LAKI-LAKI")
        self.assertFalse(checks["birthDate"])
        self.assertIn("Tanggal lahir di NIK tidak cocok dengan tanggal lahir di KTP", warnings)

    def test_jenis_kelamin_tidak_cocok(self):
        checks, _ = check_nik("3273011708050003", "2005-08-17", "PEREMPUAN")
        self.assertFalse(checks["gender"])

    def test_kode_provinsi_tidak_dikenal(self):
        checks, _ = check_nik("9973011708050003", None, None)
        self.assertFalse(checks["province"])

    def test_nik_tidak_terbaca(self):
        checks, warnings = check_nik(None, None, None)
        self.assertIsNone(checks["format"])
        self.assertIn("NIK tidak terbaca", warnings)


if __name__ == "__main__":
    unittest.main()

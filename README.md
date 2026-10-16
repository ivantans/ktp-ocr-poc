# ktp-ocr-poc

Proof of concept membaca foto KTP Indonesia dengan model OCR open-source
([PaddleOCR-VL-1.6](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6), 1B parameter),
dijalankan sendiri tanpa layanan pihak ketiga, lalu memetakan teksnya ke field KTP
dan memeriksa konsistensi NIK.

> Status: proof of concept.

## Isi

- `ktp_ocr.py` — menjalankan model (prompt `OCR:`) lalu memetakan teksnya ke field KTP.
  Menerima berkas atau folder; `--out` menulis satu JSON per foto plus `summary.json`.
- `ktp_parser.py` — pemeta field + pemeriksaan struktur NIK. Tidak bergantung model,
  bisa dipakai ulang untuk mesin OCR lain.
- `reparse.py` — memproses ulang teks mentah yang tersimpan tanpa menjalankan model lagi.
- `test_ktp_parser.py` — tes pemeta, jalan tanpa model: `python3 -m unittest -v`.
- `colab_ktp_ocr.ipynb` — menjalankan uji di GPU Google Colab.

## Menjalankan

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python ktp_ocr.py path/ke/foto-ktp.jpg --show-text
python ktp_ocr.py folder-foto/ --out results/uji-1
```

Unduhan pertama mengambil model ±2 GB dari Hugging Face. Perangkat dipilih otomatis
(`cuda` → `mps` → `cpu`), bisa dipaksa dengan `--device`. Diuji dengan transformers 5.19.

## Pemeriksaan NIK

Dari NIK dibaca kode provinsi, tanggal lahir (digit 7–12; perempuan +40 pada tanggal),
dan nomor urut, lalu dicocokkan dengan tanggal lahir dan jenis kelamin yang tercetak di KTP.

Lolos pemeriksaan berarti NIK **konsisten** dengan isi kartunya — bukan bukti NIK terdaftar
di Dukcapil. Salah baca di kode wilayah (digit 1–6) atau nomor urut (digit 13–16) tidak
tertangkap; untuk itu cocokkan dengan NIK yang diisi pengguna.

## Data pribadi

Foto KTP adalah data pribadi (UU No. 27/2022 tentang Pelindungan Data Pribadi).

- Repo ini **tidak memuat foto atau hasil OCR KTP siapa pun**. `samples/`, `results/`,
  gambar, dan zip diabaikan git.
- Data di tes adalah rekaan.
- Pakai hanya KTP sendiri atau contoh yang sudah ada izinnya, dan jangan unggah foto KTP
  orang lain ke layanan luar (termasuk Colab).

## Lisensi

Apache License 2.0 — lihat [LICENSE](LICENSE) dan [NOTICE](NOTICE). Model PaddleOCR-VL
tidak disertakan di repo ini dan berlisensi terpisah (Apache-2.0).

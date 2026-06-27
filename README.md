# Japan Weather Data Pipeline — Open-Meteo + GitHub Actions + Airflow

โปรเจกต์นี้ดึงข้อมูลอุณหภูมิรายวันของเมืองท่องเที่ยวในญี่ปุ่นจาก Open-Meteo แล้วเก็บเป็นไฟล์ CSV แบบสะสม เพื่อใช้วิเคราะห์ว่าเดือนไหนน่าไปเที่ยว และตรวจแนวโน้มว่าอุณหภูมิเปลี่ยนไปหรือไม่

## เมืองเริ่มต้น
แก้ไขได้ที่ `config/cities.csv`

- Tokyo
- Osaka
- Kyoto
- Sapporo
- Fukuoka

## Output หลัก

```text
data/
├── weather_daily_master.csv
└── weather_daily/
    └── date=YYYY-MM-DD/
        └── weather_daily_YYYY-MM-DD.csv

output/
├── monthly_travel_summary.csv
├── trend_by_city.csv
└── climate_change_monthly_delta.csv
```

## 1) Run ในเครื่องก่อน

```bash
pip install -r requirements.txt

# ดึงข้อมูลของเมื่อวาน
python src/fetch_open_meteo_daily.py --mode yesterday

# Backfill ย้อนหลัง เช่น 2000-01-01 ถึง 2026-06-26
python src/fetch_open_meteo_daily.py \
  --start-date 2000-01-01 \
  --end-date 2026-06-26 \
  --cities config/cities.csv \
  --out data/weather_daily

# สร้างไฟล์วิเคราะห์
python src/analyze_weather_trends.py --master data/weather_daily_master.csv --out output
```

## 2) Run บน GitHub Actions

1. สร้าง GitHub repository ใหม่
2. Upload ไฟล์ทั้งหมดในโปรเจกต์นี้ขึ้น repository
3. ไปที่ `Settings > Actions > General`
4. ที่ `Workflow permissions` เลือก `Read and write permissions`
5. ไปที่แท็บ `Actions`
6. เลือก workflow: `Daily Japan Weather Pipeline`
7. กด `Run workflow`

### Backfill ครั้งแรก
ใส่ input เช่น:

```text
start_date = 2000-01-01
end_date   = 2026-06-26
```

หลังจากนั้น workflow จะ run ทุกวันอัตโนมัติ และ commit ไฟล์ใหม่กลับเข้า repository

## 3) Run บน Airflow

วางทั้ง folder นี้ไว้ใน Airflow DAG folder เช่น:

```text
/opt/airflow/dags/japan-weather-pipeline/
```

ติดตั้ง dependency ใน Airflow environment:

```bash
pip install -r /opt/airflow/dags/japan-weather-pipeline/requirements.txt
```

จากนั้นใน Airflow UI จะเห็น DAG:

```text
japan_weather_openmeteo_daily
```

DAG จะดึงข้อมูลเมื่อวานทุกวัน เวลา 08:15 ตามเวลา Japan Time แล้วสร้างไฟล์ output ให้

## 4) วิเคราะห์เดือนน่าเที่ยว

ดูไฟล์:

```text
output/monthly_travel_summary.csv
```

คอลัมน์สำคัญ:

- `avg_temp_mean_c` = อุณหภูมิเฉลี่ยของเดือนนั้น
- `avg_monthly_precip_mm` = ปริมาณฝนเฉลี่ยต่อเดือน
- `travel_score_0_100` = คะแนนความน่าเที่ยวแบบง่าย ๆ โดยให้น้ำหนักอุณหภูมิ 65% และฝน 35%

## 5) วิเคราะห์ผลกระทบจากโลกร้อน

ดูไฟล์:

```text
output/trend_by_city.csv
output/climate_change_monthly_delta.csv
```

- `trend_by_city.csv` แสดงแนวโน้มอุณหภูมิ °C ต่อทศวรรษ
- `climate_change_monthly_delta.csv` เปรียบเทียบค่าเฉลี่ย 2000–2009 กับ 2016–2025 แยกรายเมืองและรายเดือน

## หมายเหตุ

- การ run รายวันควรดึง “เมื่อวาน” เพราะข้อมูลของวันนี้ยังไม่สมบูรณ์
- GitHub Actions ใช้เวลา UTC ใน cron ดังนั้น `37 1 * * *` คือ 10:37 ที่ญี่ปุ่น และ 08:37 ที่ไทย
- Open-Meteo free API เหมาะกับงานเรียน/งาน non-commercial และไม่ต้องใช้ API key

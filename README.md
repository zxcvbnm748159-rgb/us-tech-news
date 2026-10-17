# 📈 US Tech Stock News & Analytics Portal

แพลตฟอร์มดึงข่าว แปลภาษา วิเคราะห์เชิงลึก และติดตามราคาหุ้นเทคโนโลยีสหรัฐฯ แบบเรียลไทม์ ออกแบบด้วยสถาปัตยกรรม **Offline-first Static Web App** ทำงานร่วมกับ **GitHub Actions (Automation Pipeline)** โดยไม่ต้องมีเซิร์ฟเวอร์หลัก (Serverless) และรองรับการดูผลวิเคราะห์จาก AI โดยไม่ต้องกรอก API Key บนหน้าเว็บ

---

## 🌟 ฟีเจอร์หลัก (Key Features)

* **🤖 AI-Powered Stock Analysis:** สรุปข่าว แปลภาษาไทย และวิเคราะห์ผลกระทบเชิงลึกรายหุ้น 3 ประเด็นด้วย Gemini AI โดยประมวลผลล่วงหน้าลงไฟล์ JSON
* **⏱️ 48-Hour News Window:** คัดกรองและแสดงเฉพาะข่าวสดใหม่ในรอบ 48 ชั่วโมงล่าสุด พร้อมจัดหมวดหมู่ (`AI`, `Hardware`, `Financial`, `General`)
* **📊 Stock Detail & Watchlist Dashboard:**
* แดชบอร์ดแสดงข้อมูลราคาหุ้น realtime / after-hours
* Sparkline chart และกราฟจาก TradingView Widget
* ตัวเลขสถิติการเงินสำคัญ (Market Cap, EPS, 52W High/Low, Beta)
* ระบบบันทึกรายการหุ้นเฝ้าติดตาม (Watchlist) และบันทึกข่าว (Bookmarks) เก็บลง `localStorage`


* **🚀 Fast & Offline-First:** โหลดหน้าเว็บเร็ว ไร้ปัญหา CORS Policy และมีระบบ Fallback รองรับเมื่อไฟล์ข้อมูลอยู่ระหว่างการประมวลผล
* **🛡️ Continuous Integration & Automated Testing:** มีระบบทดสอบความถูกต้องของสคริปต์และ Schema JSON ผ่าน Pytest ก่อน Deploy ทุกครั้ง

---

## 🏗️ สถาปัตยกรรมระบบ (System Architecture)

```
[ Yahoo Finance RSS / Financial Data ]
                 │
                 ▼
     [ GitHub Actions Automation ]
  (fetch_news.py / fetch_market_data.py)
                 │
                 ├─► 1. Gemini AI Analysis (Summarize & Categorize)
                 ├─► 2. Generate JSON (stock_analysis.json, market_prices.json)
                 └─► 3. Pytest & Schema Verification
                 │
                 ▼
        [ GitHub Pages (Frontend) ]
 (index.html อ่านไฟล์ JSON พร้อม Cache-Busting Timestamp)

```

---

## 📂 โครงสร้างไฟล์ในโปรเจกต์ (Directory Structure)

```text
.
├── .github/
│   ├── actions/
│   │   └── notify-telegram/        # Action ส่วนกลางสำหรับแจ้งเตือน Telegram เมื่อ Workflow ล้มเหลว
│   └── workflows/
│       ├── test.yml                # CI/CD: รัน Pytest เมื่อ Push, PR หรือ Manual Trigger
│       └── update.yml              # Automation: ดึงข่าว แปลภาษา วิเคราะห์ และอัปเดตไฟล์ JSON
├── data/
│   ├── news.json                   # ข่าวสารรวมทุกหมวดหมู่
│   ├── stock_analysis.json         # บทวิเคราะห์ AI รายหุ้น
│   └── market_prices.json          # ข้อมูลราคาหุ้นและตัวเลขทางการเงิน
├── scripts/
│   ├── fetch_news.py               # สคริปต์ดึง RSS, ส่ง Gemini AI และบันทึก JSON
│   └── fetch_market_data.py        # สคริปต์ดึงราคาหุ้นและข้อมูลการเงิน
├── tests/
│   ├── test_data_schema.py         # ตรวจสอบโครงสร้าง Schema ของ JSON
│   └── test_market_features.py     # ตรวจสอบระบบคัดกรองข่าว 48ชม. และ Fallback
├── index.html                      # หน้าต่าง Dashboard หลัก (Frontend UI)
├── requirements.txt                # Python Dependencies
└── README.md

```

---

## 🛠️ การตั้งค่าและการใช้งาน (Setup & Usage)

### 1. การติดตั้งสำหรับใช้งาน/พัฒนาในเครื่อง (Local Development)

1. **Clone Repository:**
```bash
git clone https://github.com/<your-username>/us-tech-news.git
cd us-tech-news

```


2. **ติดตั้ง Python Dependencies:**
```bash
pip install -r requirements.txt

```


3. **ตั้งค่า Environment Variable สำหรับ Gemini API:**
```bash
export GEMINI_API_KEY="your-gemini-api-key"

```


4. **สั่งรันสคริปต์ดึงข้อมูลทดสอบ:**
```bash
python scripts/fetch_news.py
python scripts/fetch_market_data.py

```


5. **รันการทดสอบ (Automated Tests):**
```bash
pytest

```



---

### 2. การตั้งค่าบน GitHub Secrets & Notifications

เพื่อให้ระบบทำงานอัตโนมัติบน GitHub Actions และแจ้งเตือนเมื่อเกิดข้อผิดพลาด ให้ตั้งค่าต่าง ๆ ดังนี้:

#### 🔑 Repository Secrets (สำหรับ Gemini API & Telegram Alerts)

ไปที่ **Settings > Secrets and variables > Actions** แล้วเพิ่ม Secrets ต่อไปนี้:

| Secret Name | คำอธิบาย | ความจำเป็น |
| --- | --- | --- |
| `GEMINI_API_KEY` | API Key จาก Google AI Studio สำหรับใช้สรุปและวิเคราะห์ข่าว | **จำเป็นมาก** |
| `TELEGRAM_BOT_TOKEN` | Token ของ Telegram Bot สำหรับรับแจ้งเตือนเมื่อ Workflow Failure | *ไม่บังคับ* (ข้ามได้ถ้าไม่ใช้) |
| `TELEGRAM_CHAT_ID` | Chat ID ของผู้รับแจ้งเตือนใน Telegram | *ไม่บังคับ* (ข้ามได้ถ้าไม่ใช้) |

> ℹ️ **หมายเหตุเกี่ยวกับ Telegram Alert:** หากไม่ได้ตั้งค่า Secrets ระบบจะข้ามการส่งแจ้งเตือน Telegram โดยอัตโนมัติโดยไม่ทำให้ Workflow ล้มเหลว

#### 📧 Email Notifications

หากต้องการรับแจ้งเตือนผ่านอีเมลเมื่อ GitHub Actions ล้มเหลว สามารถเปิดใช้งานได้ที่:

* **GitHub Settings > Notifications > Actions** -> เลือกรับอีเมลเมื่อเกิดข้อผิดพลาด (Failed workflows)

---

## 🔄 ระบบการทำงานอัตโนมัติ (Automated CI/CD Pipeline)

1. **`test.yml` (CI Workflow):**
* ทำงานอัตโนมัติเมื่อมีการ **Push**, **Pull Request** หรือสั่งรันผ่าน **Workflow Dispatch**
* ติดตั้ง Dependencies จาก `requirements.txt` และรัน `pytest` ตรวจสอบ Schema ของ JSON และฟังก์ชันคัดกรองข่าว
* หากล้มเหลว จะเรียกใช้งาน `notify-telegram` เพื่อส่งข้อความแจ้งเตือน


2. **`update.yml` (Data Pipeline Workflow):**
* ทำงานตามรอบเวลา (Cron Job) และสั่งรันเองได้
* ดึงข่าวสดใหม่ ประมวลผลบทวิเคราะห์ และ Commit ไฟล์ `data/*.json` กลับเข้า Repository
* หน้าเว็บ `index.html` จะดึงข้อมูลใหม่มาแสดงผลทันทีโดยใช้ Timestamp Query Parameter (`?t=timestamp`) เพื่อป้องกันปัญหา Browser Caching



---

## 📄 License & Disclaimer

* **Disclaimer:** ข้อมูล ข่าวสาร และการวิเคราะห์โดย AI บนเว็บไซต์นี้จัดทำเพื่อการศึกษาและให้ข้อมูลเท่านั้น **ไม่ถือเป็นคำแนะนำทางการลงทุน (Not Financial Advice)** โปรดตรวจสอบข้อมูลจากแหล่งข่าวต้นฉบับก่อนตัดสินใจลงทุนทุกครั้ง

---
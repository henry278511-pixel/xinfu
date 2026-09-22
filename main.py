import os
import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
import pandas as pd
from io import StringIO
from datetime import datetime, timezone, timedelta

# ==================== 環境變數 ====================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

# 取得台灣時間日期 (YYYY/MM/DD)
tw_tz = timezone(timedelta(hours=8))
today_tw = datetime.now(tw_tz).strftime('%Y/%m/%d')
today_display = datetime.now(tw_tz).strftime('%Y/%m/%d (週%w)').replace('週0', '週日').replace('週1', '週一').replace('週2', '週二').replace('週3', '週三').replace('週4', '週四').replace('週5', '週五').replace('週6', '週六')

# ==================== 1. 抓取期交所三大法人未平倉 ====================
def get_taifex_summary():
    try:
        url = "https://www.taifex.com.tw/cht/3/futContractsDateDown"
        payload = {
            'queryStartDate': today_tw,
            'queryEndDate': today_tw
        }
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.post(url, data=payload, headers=headers, timeout=15)
        res.encoding = 'big5'
        
        if "查無資料" in res.text or not res.text.strip():
            return f"📊 臺指期未平倉 ({today_display})\n⚠️ 今日尚無期交所資料或為休市日"

        df = pd.read_csv(StringIO(res.text))
        df.columns = [c.strip() for c in df.columns]
        
        target_map = {
            '臺股期貨': '台指期',
            '電子期貨': '電子期',
            '金融期貨': '金融期',
            '小型臺指期貨': '小台指'
        }
        
        text_lines = [f"📊 臺指期未平倉\n{today_display}", "商品  淨未平倉量 (淨交易量)", "------------------------"]
        
        for raw_name, display_name in target_map.items():
            sub = df[df['商品名稱'].astype(str).str.strip() == raw_name]
            if sub.empty:
                continue
            text_lines.append(f"【{display_name}】")
            for id_type in ['自營商', '投信', '外資及陸資']:
                row = sub[sub['身份別'].astype(str).str.strip() == id_type]
                short_id = '外資' if '外資' in id_type else id_type
                if not row.empty:
                    net_oi = int(row['多空淨額未平倉口數'].values[0])
                    net_trade = int(row['多空淨額交易口數'].values[0])
                    sign = "+" if net_trade > 0 else ""
                    text_lines.append(f"  {short_id}: {net_oi} ({sign}{net_trade})")
            text_lines.append("")
            
        return "\n".join(text_lines).strip()
    except Exception as e:
        print(f"抓取期交所資料失敗: {e}")
        return f"📊 臺指期未平倉 ({today_display})\n今日資料擷取略過"

# ==================== 2. 抓取永豐期貨最新研報 PDF ====================
def get_latest_pdf():
    try:
        list_url = "https://www.spf.com.tw/sinopacSPF/research/list.do?id=1709f20d3ff00000d8e2039e8984ed51"
        res = requests.get(list_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        
        pdf_url = None
        for a in soup.find_all("a", href=True):
            if "researchContent" in a["href"] and a["href"].endswith(".pdf"):
                href = a["href"]
                pdf_url = href if href.startswith("http") else "https://www.spf.com.tw" + href
                break
                
        if not pdf_url:
            print("未找到 PDF 連結")
            return []
            
        print(f"下載 PDF: {pdf_url}")
        pdf_data = requests.get(pdf_url, timeout=30).content
        with open("report.pdf", "wb") as f:
            f.write(pdf_data)
            
        # PDF 轉圖片
        doc = fitz.open("report.pdf")
        images = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=180)
            img_name = f"page_{i+1}.png"
            pix.save(img_name)
            images.append(img_name)
        doc.close()
        return images
    except Exception as e:
        print(f"下載/轉換 PDF 失敗: {e}")
        return []

# ==================== 3. 免費圖床託管 (Catbox) ====================
def upload_image(filepath):
    try:
        with open(filepath, 'rb') as f:
            res = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
                timeout=30
            )
            if res.status_code == 200 and res.text.startswith("http"):
                return res.text.strip()
    except Exception as e:
        print(f"上傳圖片失敗: {e}")
    return None

# ==================== 4. LINE 推播 ====================
def push_line(text, image_urls):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("未設定 LINE 金鑰，無法發送")
        return

    messages = [{"type": "text", "text": text}]
    for img_url in image_urls:
        messages.append({
            "type": "image",
            "originalContentUrl": img_url,
            "previewImageUrl": img_url
        })
        
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    body = {
        "to": LINE_USER_ID,
        "messages": messages
    }
    
    res = requests.post("https://api.line.me/v2/bot/message/push", json=body, headers=headers)
    print("LINE 發送結果:", res.status_code, res.text)

# ==================== 主流程 ====================
if __name__ == "__main__":
    print("開始執行盤後推播腳本...")
    # 1. 整理三大法人未平倉文字
    summary_text = get_taifex_summary()
    
    # 2. 下載研報並轉為圖片
    img_files = get_latest_pdf()
    
    # 3. 上傳圖片取得 HTTPS 網址
    uploaded_urls = []
    for img in img_files:
        url = upload_image(img)
        if url:
            uploaded_urls.append(url)
            
    # 4. 發送 LINE
    push_line(summary_text, uploaded_urls)
    print("腳本執行完畢！")

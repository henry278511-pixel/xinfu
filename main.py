import os
import re
import requests
import fitz  # PyMuPDF
import pandas as pd
from io import StringIO
from datetime import datetime, timezone, timedelta
import urllib3

# 關閉 SSL 憑證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 環境變數 ====================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

# 台灣時間
tw_tz = timezone(timedelta(hours=8))
now_tw = datetime.now(tw_tz)
today_tw = now_tw.strftime('%Y/%m/%d')
today_display = now_tw.strftime('%Y/%m/%d (週%w)').replace('週0', '週日').replace('週1', '週一').replace('週2', '週二').replace('週3', '週三').replace('週4', '週四').replace('週5', '週五').replace('週6', '週六')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ==================== 1. 抓取期交所三大法人未平倉 ====================
def get_taifex_summary():
    try:
        url = f"https://www.taifex.com.tw/cht/3/futContractsDateView?queryStartDate={today_tw}&queryEndDate={today_tw}"
        print(f"正在抓取期交所數據: {url}")
        res = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        res.encoding = 'big5'
        
        if "查無資料" in res.text or len(res.text.strip()) < 50:
            print("期交所回傳查無資料或內容為空")
            return f"📊 臺指期未平倉 ({today_display})\n⚠️ 今日尚無期交所資料或為休市日"

        df = pd.read_csv(StringIO(res.text))
        df.columns = [str(c).strip() for c in df.columns]
        
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
                    net_oi = int(str(row['多空淨額未平倉口數'].values[0]).replace(',', ''))
                    net_trade = int(str(row['多空淨額交易口數'].values[0]).replace(',', ''))
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
        print(f"正在搜尋永豐期貨研報: {list_url}")
        res = requests.get(list_url, headers=HEADERS, timeout=15, verify=False)
        
        # 用正則表達式精準抓取 PDF 相對路徑
        pdf_matches = re.findall(r'(/upload/sinopac/researchContent/[a-zA-Z0-9]+\.pdf)', res.text)
        if not pdf_matches:
            print("網頁中未匹配到 PDF 路徑")
            return []
            
        # 取前 1~2 份最新報告（通常是當日的盤後快訊與籌碼快訊）
        pdf_urls = ["https://www.spf.com.tw" + p for p in dict.fromkeys(pdf_matches)[:2]]
        print(f"找到最新 PDF: {pdf_urls}")
        
        images = []
        for idx, pdf_url in enumerate(pdf_urls):
            pdf_data = requests.get(pdf_url, headers=HEADERS, timeout=30, verify=False).content
            pdf_path = f"report_{idx+1}.pdf"
            with open(pdf_path, "wb") as f:
                f.write(pdf_data)
                
            doc = fitz.open(pdf_path)
            # 轉換第一頁與第二頁（每份快訊最關鍵的兩頁）
            for page_idx in range(min(len(doc), 2)):
                pix = doc[page_idx].get_pixmap(dpi=180)
                img_name = f"doc_{idx+1}_page_{page_idx+1}.png"
                pix.save(img_name)
                images.append(img_name)
            doc.close()
            
        return images
    except Exception as e:
        print(f"下載/轉換 PDF 失敗: {e}")
        return []

# ==================== 3. 免費圖床託管 (雙重備援) ====================
def upload_image(filepath):
    # 管道 1: Catbox
    try:
        with open(filepath, 'rb') as f:
            res = requests.post("https://catbox.moe/user/api.php", data={"reqtype": "fileupload"}, files={"fileToUpload": f}, timeout=20)
            if res.status_code == 200 and res.text.startswith("http"):
                url = res.text.strip()
                print(f"Catbox 上傳成功: {url}")
                return url
    except Exception as e:
        print(f"Catbox 失敗: {e}")

    # 管道 2: Tmpfiles (備援)
    try:
        with open(filepath, 'rb') as f:
            res = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f}, timeout=20)
            if res.status_code == 200:
                raw_url = res.json().get("data", {}).get("url")
                if raw_url:
                    dl_url = raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                    print(f"Tmpfiles 上傳成功: {dl_url}")
                    return dl_url
    except Exception as e:
        print(f"Tmpfiles 失敗: {e}")

    return None

# ==================== 4. LINE 推播 ====================
def push_line(text, image_urls):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("未設定 LINE 金鑰")
        return

    messages = [{"type": "text", "text": text}]
    # LINE 單次推播最多支援 5 則訊息（1 則文字 + 最多 4 張圖片）
    for img_url in image_urls[:4]:
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
    summary_text = get_taifex_summary()
    img_files = get_latest_pdf()
    
    uploaded_urls = []
    for img in img_files:
        url = upload_image(img)
        if url:
            uploaded_urls.append(url)
            
    push_line(summary_text, uploaded_urls)
    print("腳本執行完畢！")

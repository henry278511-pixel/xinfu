from datetime import datetime, timedelta, timezone
import os
import re
import urllib3
from bs4 import BeautifulSoup
import pymupdf
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 環境變數 ====================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

tw_tz = timezone(timedelta(hours=8))
now_tw = datetime.now(tw_tz)
today_tw = now_tw.strftime("%Y/%m/%d")
today_display = (
    now_tw.strftime("%Y/%m/%d (週%w)")
    .replace("週0", "週日")
    .replace("週1", "週一")
    .replace("週2", "週二")
    .replace("週3", "週三")
    .replace("週4", "週四")
    .replace("週5", "週五")
    .replace("週6", "週六")
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


# ==================== 1. 抓取期交所三大法人未平倉 ====================
# ==================== 1. 抓取期交所三大法人未平倉 ====================
def get_taifex_summary():
  try:
    url = "https://www.taifex.com.tw/cht/3/futContractsDate"
    payload = {
        "queryType": "1",
        "goBackType": "",
        "queryDate": today_tw,
        "commodity_id": "all",
    }
    print(f"正在查詢期交所三大法人行情: {today_tw}")
    res = requests.post(
        url, data=payload, headers=HEADERS, timeout=15, verify=False
    )
    res.encoding = "utf-8"

    soup = BeautifulSoup(res.text, "html.parser")
    target_prods = ["臺股期貨", "電子期貨", "金融期貨", "小型臺指期貨"]
    display_names = {
        "臺股期貨": "台指期",
        "電子期貨": "電子期",
        "金融期貨": "金融期",
        "小型臺指期貨": "小台指",
    }

    current_prod = ""
    data = {}

    for tr in soup.find_all("tr"):
      tds = [td.get_text(strip=True) for td in tr.find_all("td")]

      # 第一列（含商品名稱）：直接依序解構，不需寫中括號索引
      if len(tds) >= 14:
        _, prod_name, id_type, _, _, _, _, net_trade, _, _, _, _, _, net_oi, *_ = (
            tds
        )

        for tp in target_prods:
          if tp in prod_name:
            current_prod = tp
            break
        else:
          current_prod = ""

      # 第二、三列（投信、外資）：直接依序解構
      elif len(tds) >= 12 and current_prod:
        id_type, _, _, _, _, net_trade, _, _, _, _, _, net_oi, *_ = tds
      else:
        continue

      if current_prod:
        if current_prod not in data:
          data[current_prod] = []
        data[current_prod].append((id_type, net_oi, net_trade))

    if not data:
      print("期交所查無資料或為休市日")
      return f"{today_display}\n\n⚠️ 今日尚無期交所資料或為休市日"

    # 依照您指定的風格排版
    text_lines = [
        today_display,
        "",
        "商品            淨未平倉量 (淨交易量)",
        "------------------------------------",
    ]

    for p in target_prods:
      if p in data:
        text_lines.append(display_names[p])
        for id_type, net_oi, net_trade in data[p]:
          short_id = "外資" if "外資" in id_type else id_type

          try:
            oi_num = int(net_oi.replace(",", ""))
            net_oi_str = str(oi_num)
          except:
            net_oi_str = net_oi.replace(",", "")

          try:
            t_val = int(net_trade.replace(",", ""))
            sign = "+" if t_val >= 0 else ""
            net_trade_str = f"{sign}{t_val}"
          except:
            net_trade_str = net_trade

          text_lines.append(
              f"  {short_id:<4} {net_oi_str:>10} ({net_trade_str:>6})"
          )
        text_lines.append("")

    text_lines.append(f"資料日期：{today_tw}")
    return "\n".join(text_lines).strip()

  except Exception as e:
    print(f"抓取期交所資料失敗: {e}")
    return f"📊 臺指期未平倉 ({today_display})\n今日資料擷取略過"


# ==================== 2. 抓取永豐期貨最新研報 PDF ====================
def get_latest_pdf():
  try:
    list_url = "https://www.spf.com.tw/sinopacSPF/research/list.do?id=1709f20d3ff00000d8e2039e8984ed51"
    res = requests.get(list_url, headers=HEADERS, timeout=15, verify=False)

    pdf_matches = re.findall(
        r"(/upload/sinopac/researchContent/[a-zA-Z0-9]+\.pdf)", res.text
    )
    if not pdf_matches:
      print("網頁中未匹配到 PDF 路徑")
      return []

    unique_matches = list(dict.fromkeys(pdf_matches))[:2]
    pdf_urls = ["https://www.spf.com.tw" + p for p in unique_matches]
    print(f"找到最新 PDF: {pdf_urls}")

    images = []
    for idx, pdf_url in enumerate(pdf_urls):
      pdf_data = requests.get(
          pdf_url, headers=HEADERS, timeout=30, verify=False
      ).content
      pdf_path = f"report_{idx+1}.pdf"
      with open(pdf_path, "wb") as f:
        f.write(pdf_data)

      doc = pymupdf.open(pdf_path)
      for page_idx in range(min(len(doc), 2)):
        pix = doc[page_idx].get_pixmap(dpi=150)
        img_name = f"doc_{idx+1}_page_{page_idx+1}.png"
        pix.save(img_name)
        images.append(img_name)
      doc.close()

    return images
  except Exception as e:
    print(f"下載/轉換 PDF 失敗: {e}")
    return []


# ==================== 3. 直連圖床 (Imgur + Freeimage) ====================
def upload_image(filepath):
  try:
    headers = {"Authorization": "Client-ID 546c25a59c58ad7"}
    with open(filepath, "rb") as f:
      res = requests.post(
          "https://api.imgur.com/3/image",
          headers=headers,
          files={"image": f},
          timeout=20,
      )
    data = res.json()
    if data.get("success"):
      link = data["data"]["link"]
      print(f"Imgur 上傳成功: {link}")
      return link
  except Exception as e:
    print(f"Imgur 失敗: {e}")

  try:
    with open(filepath, "rb") as f:
      res = requests.post(
          "https://freeimage.host/api/1/upload",
          data={
              "key": "6d207e02198a847aa98d0a2a901485a5",
              "action": "upload",
          },
          files={"source": f},
          timeout=20,
      )
    data = res.json()
    if data.get("status_code") == 200:
      link = data["image"]["url"]
      print(f"Freeimage 上傳成功: {link}")
      return link
  except Exception as e:
    print(f"Freeimage 失敗: {e}")

  return None


# ==================== 4. LINE 推播 ====================
# ==================== 4. LINE 廣播群發 (發給所有好友) ====================
def push_line(summary_msg, image_urls):
  if not LINE_CHANNEL_ACCESS_TOKEN:
    print("未設定 LINE_CHANNEL_ACCESS_TOKEN")
    return

  # 自動判斷是 Flex 卡片物件還是純文字
  if isinstance(summary_msg, dict):
    messages = [summary_msg]
  else:
    messages = [{"type": "text", "text": str(summary_msg)}]

  for img_url in image_urls[:4]:
    messages.append({
        "type": "image",
        "originalContentUrl": img_url,
        "previewImageUrl": img_url,
    })

  headers = {
      "Content-Type": "application/json",
      "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
  }
  # 廣播不需要指定 "to"，只需帶上 messages
  body = {"messages": messages}

  # 改用 broadcast API 端點
  res = requests.post(
      "https://api.line.me/v2/bot/message/broadcast", json=body, headers=headers
  )
  print("LINE 廣播發送結果:", res.status_code, res.text)


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

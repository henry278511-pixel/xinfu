from datetime import datetime, timedelta, timezone
import json
import os
import re
import urllib3
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
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


# ==================== 1. 抓取期交所三大法人未平倉 (保留原汁原味內容) ====================
def get_taifex_data():
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

    current_prod = ""
    data = {}

    for tr in soup.find_all("tr"):
      tds = [td.get_text(strip=True) for td in tr.find_all("td")]

      # 第一列（含序號與商品名稱）
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

      # 第二、三列（投信、外資）
      elif len(tds) >= 12 and current_prod:
        id_type, _, _, _, _, net_trade, _, _, _, _, _, net_oi, *_ = tds
      else:
        continue

      if current_prod:
        if current_prod not in data:
          data[current_prod] = []
        data[current_prod].append((id_type, net_oi, net_trade))

    return data

  except Exception as e:
    print(f"抓取期交所資料失敗: {e}")
    return {}


# ==================== 1-A. 原版 Flex Message 資訊卡 (完全保留) ====================
def build_taifex_flex(data):
  display_names = {
      "臺股期貨": "台指期",
      "電子期貨": "電子期",
      "金融期貨": "金融期",
      "小型臺指期貨": "小台指",
  }
  target_prods = ["臺股期貨", "電子期貨", "金融期貨", "小型臺指期貨"]

  if not data:
    return {
        "type": "text",
        "text": f"📊 臺指期未平倉 ({today_display})\n⚠️ 今日尚無期交所資料或為休市日",
    }

  body_contents = [
      {
          "type": "text",
          "text": today_display,
          "weight": "bold",
          "size": "md",
          "color": "#339af0",
          "align": "center",
      },
      {
          "type": "box",
          "layout": "horizontal",
          "margin": "lg",
          "contents": [
              {
                  "type": "text",
                  "text": "商品",
                  "size": "xs",
                  "color": "#868e96",
                  "flex": 3,
              },
              {
                  "type": "text",
                  "text": "淨未平倉量 (淨交易量)",
                  "size": "xs",
                  "color": "#868e96",
                  "align": "end",
                  "flex": 7,
              },
          ],
      },
      {"type": "separator", "margin": "xs", "color": "#495057"},
  ]

  for p in target_prods:
    if p in data:
      body_contents.append({
          "type": "text",
          "text": display_names[p],
          "weight": "bold",
          "size": "sm",
          "color": "#339af0",
          "margin": "md",
      })

      for id_type, net_oi, net_trade in data[p]:
        short_id = "外資" if "外資" in id_type else id_type
        oi_str = net_oi.replace(",", "")
        try:
          t_val = int(net_trade.replace(",", ""))
          sign = "+" if t_val >= 0 else ""
          net_trade_str = f"{sign}{t_val}"
        except:
          net_trade_str = net_trade

        val_color = "#51cf66" if "-" in oi_str else "#ff922b"

        body_contents.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "xs",
            "contents": [
                {
                    "type": "text",
                    "text": f"  {short_id}",
                    "size": "xs",
                    "color": "#ced4da",
                    "flex": 3,
                },
                {
                    "type": "text",
                    "text": f"{oi_str} ({net_trade_str})",
                    "size": "xs",
                    "color": val_color,
                    "align": "end",
                    "flex": 7,
                },
            ],
        })

  body_contents.append(
      {"type": "separator", "margin": "md", "color": "#495057"}
  )
  body_contents.append({
      "type": "text",
      "text": f"資料日期: {today_tw}",
      "size": "xxs",
      "color": "#868e96",
      "align": "center",
      "margin": "sm",
  })

  return {
      "type": "flex",
      "altText": f"臺指期未平倉 ({today_display})",
      "contents": {
          "type": "bubble",
          "size": "kilo",
          "styles": {"body": {"backgroundColor": "#282a36"}},
          "body": {
              "type": "box",
              "layout": "vertical",
              "contents": body_contents,
          },
      },
  }


# ==================== 1-B. 將原版資訊卡繪製成「同款高解析圖檔」 (方便一鍵轉傳分享) ====================
def create_taifex_summary_image(data):
  if not data:
    return None

  # 支援繁體中文字型與負號顯示
  plt.rcParams["font.sans-serif"] = [
      "Noto Sans CJK TC",
      "Microsoft JhengHei",
      "PingFang TC",
      "WenQuanYi Micro Hei",
      "sans-serif",
  ]
  plt.rcParams["axes.unicode_minus"] = False

  display_names = {
      "臺股期貨": "台指期",
      "電子期貨": "電子期",
      "金融期貨": "金融期",
      "小型臺指期貨": "小台指",
  }
  target_prods = ["臺股期貨", "電子期貨", "金融期貨", "小型臺指期貨"]

  fig, ax = plt.subplots(figsize=(5.5, 7.5), dpi=200)
  fig.patch.set_facecolor("#282a36")
  ax.set_facecolor("#282a36")
  ax.axis("off")

  # 標題
  ax.text(
      0.5,
      0.95,
      today_display,
      fontsize=14,
      fontweight="bold",
      color="#339af0",
      ha="center",
      va="top",
  )

  # 表頭
  ax.text(
      0.08,
      0.89,
      "商品",
      fontsize=10,
      fontweight="bold",
      color="#868e96",
      ha="left",
      va="top",
  )
  ax.text(
      0.92,
      0.89,
      "淨未平倉量 (淨交易量)",
      fontsize=10,
      fontweight="bold",
      color="#868e96",
      ha="right",
      va="top",
  )
  ax.plot([0.08, 0.92], [0.865, 0.865], color="#495057", lw=1)

  y = 0.83
  for p in target_prods:
    if p in data:
      # 商品標題 (藍字)
      ax.text(
          0.08,
          y,
          display_names[p],
          fontsize=11,
          fontweight="bold",
          color="#339af0",
          ha="left",
          va="top",
      )
      y -= 0.042

      for id_type, net_oi, net_trade in data[p]:
        short_id = "外資" if "外資" in id_type else id_type
        oi_str = net_oi.replace(",", "")
        try:
          t_val = int(net_trade.replace(",", ""))
          sign = "+" if t_val >= 0 else ""
          net_trade_str = f"{sign}{t_val}"
        except:
          net_trade_str = net_trade

        val_color = "#51cf66" if "-" in oi_str else "#ff922b"

        # 身分別
        ax.text(
            0.12,
            y,
            f"  {short_id}",
            fontsize=10,
            color="#ced4da",
            ha="left",
            va="top",
        )
        # 淨未平倉量 (淨交易量)
        ax.text(
            0.92,
            y,
            f"{oi_str} ({net_trade_str})",
            fontsize=10,
            fontweight="bold",
            color=val_color,
            ha="right",
            va="top",
        )
        y -= 0.038

      y -= 0.012

  ax.plot([0.08, 0.92], [y, y], color="#495057", lw=1)
  y -= 0.035
  ax.text(
      0.5,
      y,
      f"資料日期: {today_tw}",
      fontsize=8,
      color="#868e96",
      ha="center",
      va="top",
  )

  img_path = "taifex_summary.png"
  plt.savefig(img_path, bbox_inches="tight", facecolor="#282a36", dpi=200)
  plt.close()
  print(f"原版資訊卡已成功轉為圖檔: {img_path}")
  return img_path


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


# ==================== 4. LINE 廣播群發 (全部以圖片發送，支援一鍵分享) ====================
def push_line(image_urls, flex_card=None):
  if not LINE_CHANNEL_ACCESS_TOKEN:
    print("未設定 LINE_CHANNEL_ACCESS_TOKEN")
    return

  messages = []

  # 若您仍想保留原版 Flex 資訊卡，可解除註解此段：
  # if flex_card:
  #     messages.append(flex_card)

  # 將包含「原版未平倉圖卡」與「永豐研報圖片」全部以原生圖片發送 (LINE 單次最多 5 則訊息)
  for img_url in image_urls[:5]:
    messages.append({
        "type": "image",
        "originalContentUrl": img_url,
        "previewImageUrl": img_url,
    })

  headers = {
      "Content-Type": "application/json",
      "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
  }

  body = {"messages": messages}
  res = requests.post(
      "https://api.line.me/v2/bot/message/broadcast", json=body, headers=headers
  )
  print("LINE 廣播發送結果:", res.status_code, res.text)


# ==================== 主流程 ====================
# ==================== 主流程 ====================
if __name__ == "__main__":
  print("開始執行盤後推播腳本...")

  # 1. 抓取期交所未平倉數據
  raw_data = get_taifex_data()

  # ⭐️【新增這 3 行休市防呆】⭐️
  # 遇國定假日、颱風假或休市查無資料時，立即退出，不發送前一天的舊圖
  if not raw_data:
    print(f"⚠️ 今日 ({today_display}) 為台股休市日，自動取消今日推播！")
    exit(0)

  # 2. 將原版未平倉資訊卡生成同款深色圖檔 (taifex_summary.png)
  summary_img = create_taifex_summary_image(raw_data)

  # 3. 抓取永豐期貨研報圖檔
  pdf_imgs = get_latest_pdf()

  # 4. 上傳圖床 (將未平倉資訊卡圖檔排在第一張)
  all_local_imgs = []
  if summary_img:
    all_local_imgs.append(summary_img)
  all_local_imgs.extend(pdf_imgs)

  uploaded_urls = []
  for img in all_local_imgs:
    url = upload_image(img)
    if url:
      uploaded_urls.append(url)

  # 5. 生成原版 Flex 備用 (若需要)
  flex_msg = build_taifex_flex(raw_data)

  # 6. 推播圖片至 LINE (第一張即為可長按轉發的未平倉資訊卡圖片)
  push_line(uploaded_urls, flex_card=None)
  print("腳本執行完畢！")

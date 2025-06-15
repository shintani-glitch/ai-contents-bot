import os
import random
import json
import requests
import time
import re
from datetime import datetime, date
import pytz
import gspread
import google.generativeai as genai
from google.oauth2.service_account import Credentials

# --- 定数と設定 ---
SPREADSHEET_NAME = 'コスメ投稿案リスト'
SERVICE_ACCOUNT_FILE = 'google_credentials.json'
WEEKDAY_SCHEDULE = {"07:00":"planner", "07:30":"planner", "08:30":"planner", "12:05":"planner", "12:30":"planner", "16:00":"planner", "17:30":"planner", "19:00":"affiliate", "20:00":"affiliate", "21:00":"affiliate", "21:45":"planner", "22:15":"affiliate", "23:00":"planner", "23:45":"planner", "00:30":"planner"}
HOLIDAY_SCHEDULE = {"09:30":"planner", "10:30":"planner", "11:30":"affiliate", "13:00":"planner", "14:30":"planner", "16:00":"affiliate", "17:30":"planner", "19:00":"planner", "20:00":"affiliate", "21:00":"affiliate", "21:45":"planner", "22:30":"affiliate", "23:15":"planner", "23:50":"affiliate", "00:30":"planner"}

# --- 初期セットアップ ---
try:
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY2')
    RAKUTEN_APP_ID = os.getenv('RAKUTEN_APP_ID')
    RAKUTEN_AFFILIATE_ID = os.getenv('RAKUTEN_AFFILIATE_ID')
    genai.configure(api_key=GEMINI_API_KEY)
    print("✅ APIキー読み込み完了")
except Exception as e:
    print(f"🛑 APIキー読み込みエラー: {e}"); raise SystemExit()

def get_gspread_client():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        return gspread.authorize(creds)
    return None

def generate_planner_post(model):
    print("  - 価値提供ツイート案を生成中...")
    theme_prompt = f"あなたは日本のSNSマーケティングの専門家です。X(Twitter)アカウント「ゆあ＠プチプラコスメ塾」のフォロワーが保存したくなるような、詳しい解説形式の投稿テーマを1つ考えてください。現在の季節感や美容トレンド（Y2Kメイク、純欲メイクなど）を考慮してください。"
    topic = model.generate_content(theme_prompt).text.strip()
    
    post_prompt = f"あなたはXアカウント「ゆあ＠プチプラコスメ塾」の運営者「ゆあ」です。以下のテーマで、読者の興味を引くタイトルから始まる、一つのまとまった読み応えのある解説記事を作成してください。文字数制限はありません。アスタリスク(*)は使わず、【】や・を使い、絵文字も交えて分かりやすくしてください。最後にハッシュタグ #プチプラコスメ #コスメ塾 を付けてください。\n# 投稿テーマ\n{topic}"
    post_content = model.generate_content(post_prompt).text.strip()
    print(f"  ✅ テーマ「{topic}」の投稿案を生成完了。")
    return {"type": "planner", "topic": topic, "content": post_content}

def generate_affiliate_post(model):
    print("  - アフィリエイト投稿案を生成中...")
    keyword_prompt = "あなたは楽天市場で化粧品を探しているトレンドに敏感な女性です。「プチプラコスメ」や「韓国コスメ」関連で、具体的な検索キーワードを1つ生成してください。(例: KATE リップモンスター)"
    keyword = model.generate_content(keyword_prompt).text.strip()
    
    params = {"applicationId": RAKUTEN_APP_ID, "affiliateId": RAKUTEN_AFFILIATE_ID, "keyword": keyword, "format": "json", "sort": "-reviewCount", "hits": 5}
    rakuten_res = requests.get("https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601", params=params)
    rakuten_res.raise_for_status()
    items = rakuten_res.json().get("Items", [])
    
    if not items:
        print(f"  ⚠️ 楽天で「{keyword}」に合う商品が見つかりませんでした。")
        return None
        
    formatted_items = "\n".join([f"- 商品名: {i['Item']['itemName']}, キャッチコピー: {i['Item']['catchcopy']}, URL: {i['Item']['affiliateUrl']}" for i in items])
    tweet_prompt = f"あなたは人気のコスメ紹介インフルエンサーです。以下の楽天の人気商品リストから、最も響く商品を1つ選び、ユーザーの口コミを要約したかのようなリアルな紹介文とアフィリエイトURLをJSON形式で返してください。\n#ルール\n- 価格に触れない\n- 100文字以内\n- #PR #楽天でみつけた神コスメ を含める\n#JSON形式\n{{\"tweet_text\": \"（紹介文）\", \"affiliate_url\": \"（URL）\"}}\n#商品リスト:\n{formatted_items}"
    
    response = model.generate_content(tweet_prompt)
    result = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
    short_url = requests.get(f"http://tinyurl.com/api-create.php?url={result['affiliate_url']}").text
    full_tweet = f"{result['tweet_text']}\n\n👇商品の詳細はこちらからチェック✨\n{short_url}"
    print(f"  ✅ アフィリエイト投稿案を生成完了: {keyword}")
    return {"type": "affiliate", "topic": f"アフィリエイト投稿: {keyword}", "content": full_tweet}

def main():
    print("🚀 コンテンツ一括生成プログラムを開始します。")
    
    jst = pytz.timezone('Asia/Tokyo')
    today_weekday = date.today().weekday()
    schedule = HOLIDAY_SCHEDULE if today_weekday >= 5 else WEEKDAY_SCHEDULE
    planner_count = list(schedule.values()).count("planner")
    affiliate_count = list(schedule.values()).count("affiliate")
    print(f"本日のタスク: フォロワー獲得投稿={planner_count}件, アフィリエイト投稿={affiliate_count}件")

    model = genai.GenerativeModel('gemini-1.5-flash')
    generated_posts = []

    # 必要な数の投稿案をすべて生成する
    print("\n--- 価値提供ツイート案の生成 ---")
    for _ in range(planner_count):
        generated_posts.append(generate_planner_post(model))
        time.sleep(20) # API制限対策
        
    print("\n--- アフィリエイト投稿案の生成 ---")
    for _ in range(affiliate_count):
        post = generate_affiliate_bot(model)
        if post: generated_posts.append(post)
        time.sleep(20)

    # スプレッドシートへの書き込み
    print("\n--- スプレッドシートへの書き込み処理 ---")
    gc = get_gspread_client()
    if not gc: print("🛑 スプレッドシートクライアント取得失敗。"); return
    
    try:
        worksheet = gc.open(SPREADSHEET_NAME).sheet1
        worksheet.clear()
        header = ['scheduled_time', 'post_type', 'content', 'status', 'posted_time', 'posted_tweet_url']
        worksheet.append_row(header)
        print("✅ スプレッドシートを準備しました。")
        
        rows_to_add = []
        # スケジュールに従って書き込むデータを作成
        for time_str, task_type in sorted(schedule.items()):
            post_to_write = next((p for p in generated_posts if p['type'] == task_type), None)
            if post_to_write:
                rows_to_add.append([time_str, task_type, post_to_write['content'], 'pending', '', ''])
                generated_posts.remove(post_to_write)
        
        if rows_to_add:
            worksheet.append_rows(rows_to_add)
            print(f"✅ スプレッドシートに{len(rows_to_add)}件の投稿案を全て書き込みました。")

    except Exception as e:
        print(f"🛑 スプレッドシート処理中にエラー: {e}")

    print("🏁 コンテンツ一括生成プログラムを終了します。")

if __name__ == "__main__":
    main()

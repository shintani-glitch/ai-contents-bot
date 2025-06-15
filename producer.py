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

# ==============================================================================
# プログラム１：価値提供ツイート案（フォロワー獲得用）
# ==============================================================================
def run_content_planner(worksheet):
    print("--- 価値提供ツイート案の生成を実行します ---")
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # テーマ生成
        theme_prompt = f"あなたは日本のSNSマーケティングの専門家です。X(Twitter)アカウント「ゆあ＠プチプラコスメ塾」のフォロワーが保存したくなるような、詳しい解説形式の投稿テーマを1つ考えてください。\n#考慮すべき状況\n- 現在の時期：{datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y年%m月')}\n- 最近の美容トレンド：Y2Kメイク、純欲メイク、中顔面短縮メイクなど\n#出力形式\n- 1行に1つのテーマで出力。番号やハイフンは不要。"
        response = model.generate_content(theme_prompt)
        topic = response.text.strip()
        print(f"✅ 生成されたテーマ: {topic}")

        # ★★★★★ プロンプトを修正（長文・単一投稿形式へ） ★★★★★
        post_prompt = f"""
あなたは、Xアカウント「ゆあ＠プチプラコスメ塾」の運営者「ゆあ」です。
プチプラコスメの専門家として、10代〜20代のフォロワーに、実践的で価値の高い情報を提供します。
以下のルールを厳守して、1つのまとまった解説記事を作成してください。

# ルール
- 親しみやすく、少し先生のような頼れる口調で書く。
- **文字数制限はありません。**一つの読み応えのある記事として、質の高い情報を盛り込むこと。
- 読者の興味を引く「タイトル」から始める。
- 箇条書きや絵文字（✨💄💡など）を効果的に使い、視覚的に分かりやすく、最後まで飽きさせない工夫をする。
- ハッシュタグ（#プチプラコスメ #コスメ塾 #美容垢さんと繋がりたい など）は、記事の最後にまとめて3〜4個入れる。
- 現在のX(Twitter)で話題の美容トレンドも意識すること。

# 投稿テーマ
{topic}
"""
        response = model.generate_content(post_prompt)
        # 生成されたテキストをそのまま一つの投稿とする
        post_content = response.text.strip()
        
        # スプレッドシートに記録
        jst = pytz.timezone('Asia/Tokyo')
        timestamp = datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')
        # C列に長文コンテンツ全体を記録
        row_to_add = [timestamp, topic, post_content]
        worksheet.append_row(row_to_add)
        print(f"✅ 長文の価値提供ツイート案を生成し、スプレッドシートに記録しました。")
        
    except Exception as e:
        print(f"🛑 価値提供ツイートの処理中にエラー: {e}")

# ==============================================================================
# プログラム２：アフィリエイト投稿案
# ==============================================================================
def run_affiliate_bot(worksheet):
    print("--- アフィリエイト投稿案の生成を実行します ---")
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # 1. キーワード生成
        keyword_prompt = "あなたは楽天市場で化粧品を探しているトレンドに敏感な女性です。「プチプラコスメ」や「韓国コスメ」関連で、具体的な検索キーワードを1つ生成してください。ブランド名や商品カテゴリ名を組み合わせるのが望ましいです。(例: KATE リップモンスター)。回答はキーワード文字列のみでお願いします。"
        response = model.generate_content(keyword_prompt)
        keyword = response.text.strip()
        print(f"✅ 生成されたキーワード: {keyword}")

        # 2. 楽天APIで検索
        params = {"applicationId": RAKUTEN_APP_ID, "affiliateId": RAKUTEN_AFFILIATE_ID, "keyword": keyword, "format": "json", "sort": "-reviewCount", "hits": 5} # 候補を5件に絞る
        response = requests.get("https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601", params=params)
        response.raise_for_status()
        items = response.json().get("Items", [])
        
        if not items:
            print("⚠️ 楽天で商品が見つかりませんでした。"); return

        # 3. ツイート文生成
        formatted_items_string = "\n".join([f"- 商品名: {item['Item']['itemName']}, キャッチコピー: {item['Item']['catchcopy']}, レビュー件数: {item['Item']['reviewCount']}, レビュー平均: {item['Item']['reviewAverage']}, URL: {item['Item']['affiliateUrl']}" for item in items])
        
        # ★★★★★ プロンプトを修正（レビュー分析風へ） ★★★★★
        tweet_prompt = f"""
あなたは、日本の消費者の口コミを分析するマーケティング専門家です。
以下の楽天市場の人気商品リスト（レビュー件数・評価が高い）を分析し、最もユーザーに響くであろう商品を1つだけ選んでください。
そして、その商品の紹介文とアフィリエイトURLをJSON形式で返してください。

# 紹介文の作成ルール
- まるで**ユーザーのリアルな口コミを要約したかのような、説得力のある文章**を作成する。
- キャッチコピーや高いレビュー評価を根拠に、「みんなが絶賛しているポイント」を強調する。
- 「価格」には触れない。
- 100文字以内にまとめる。
- ハッシュタグ「#PR」「#楽天でみつけた神コスメ」を入れる。

# JSON形式
{{
  "tweet_text": "（紹介文）",
  "affiliate_url": "（URL）"
}}
# 商品リスト
{formatted_items_string}
"""
        response = model.generate_content(tweet_prompt)
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
        result = json.loads(cleaned_response)
        
        short_url = requests.get(f"http://tinyurl.com/api-create.php?url={result['affiliate_url']}").text
        full_tweet = f"{result['tweet_text']}\n\n👇商品の詳細はこちらからチェック✨\n{short_url}"
        
        print("--- 生成された投稿案 ---")
        print(full_tweet)
        print("----------------------")
        
        # スプレッドシートに記録
        jst = pytz.timezone('Asia/Tokyo')
        timestamp = datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')
        row_to_add = [timestamp, f"アフィリエイト投稿: {keyword}", full_tweet]
        worksheet.append_row(row_to_add)
        print("✅ アフィリエイト投稿案をスプレッドシートに記録しました。")

    except Exception as e:
        print(f"🛑 アフィリエイト投稿の処理中にエラー: {e}")

# ==============================================================================
# メインの実行ロジック
# ==============================================================================
def main():
    print("🚀 コンテンツ一括生成プログラムを開始します。")
    if not all([os.getenv('GEMINI_API_KEY2'), os.getenv('RAKUTEN_APP_ID'), os.getenv('RAKUTEN_AFFILIATE_ID')]):
      print("🛑 必要なAPIキーが環境変数に設定されていません。処理を終了します。")
      return

    # スケジュールとタスク数の決定
    jst = pytz.timezone('Asia/Tokyo')
    today_weekday = date.today().weekday()
    schedule = HOLIDAY_SCHEDULE if today_weekday >= 5 else WEEKDAY_SCHEDULE
    planner_count = list(schedule.values()).count("planner")
    affiliate_count = list(schedule.values()).count("affiliate")
    print(f"本日のタスク: フォロワー獲得投稿={planner_count}件, アフィリエイト投稿={affiliate_count}件")

    # スプレッドシートの準備
    gc = get_gspread_client()
    if not gc: return
    try:
        sh = gc.open(SPREADSHEET_NAME)
        worksheet = sh.sheet1
        if not worksheet.get_all_values():
            worksheet.append_row(['生成日時', 'テーマ/キーワード', '投稿内容', 'メモ1', 'メモ2', 'メモ3'])
        worksheet.clear()
        worksheet.append_row(['生成日時', 'テーマ/キーワード', '投稿内容', 'メモ1', 'メモ2', 'メモ3'])
        print(f"✅ スプレッドシート「{SPREADSHEET_NAME}」を準備しました。")
    except Exception as e:
        print(f"🛑 スプレッドシートの準備中にエラー: {e}"); return

    # タスクの実行
    for _ in range(planner_count):
        run_content_planner(worksheet)
        time.sleep(20)
    
    for _ in range(affiliate_count):
        run_affiliate_bot(worksheet)
        time.sleep(20)

    print("🏁 コンテンツ一括生成プログラムを終了します。")

if __name__ == "__main__":
    main()

import os
import sys
import random
import json
import time
import re
from datetime import datetime, date

# --- 最初に最低限のライブラリのみをインポート ---
print("--- SCRIPT START ---")
sys.stdout.flush()

try:
    print("Importing: pytz")
    import pytz
    sys.stdout.flush()
    print("✅ pytz imported.")
except ImportError as e:
    print(f"🛑 FATAL: pytz import failed: {e}"); raise SystemExit()

# --- 定数と設定 ---
SPREADSHEET_NAME = 'コスメ投稿案リスト'
SERVICE_ACCOUNT_FILE = 'google_credentials.json'
WEEKDAY_SCHEDULE = {"07:00":"planner", "07:30":"planner", "08:30":"planner", "12:05":"planner", "12:30":"planner", "16:00":"planner", "17:30":"planner", "19:00":"affiliate", "20:00":"affiliate", "21:00":"affiliate", "21:45":"planner", "22:15":"affiliate", "23:00":"planner", "23:45":"planner", "00:30":"planner"}
HOLIDAY_SCHEDULE = {"09:30":"planner", "10:30":"planner", "11:30":"affiliate", "13:00":"planner", "14:30":"planner", "16:00":"affiliate", "17:30":"planner", "19:00":"planner", "20:00":"affiliate", "21:00":"affiliate", "21:45":"planner", "22:30":"affiliate", "23:15":"planner", "23:50":"affiliate", "00:30":"planner"}

# --- グローバル変数 ---
g_rakuten_app_id = None
g_rakuten_affiliate_id = None
g_gemini_model = None

# --- 初期セットアップ ---
def setup_apis():
    global g_rakuten_app_id, g_rakuten_affiliate_id, g_gemini_model
    print("デバッグ: setup_apis() 関数を開始します。")
    sys.stdout.flush()
    try:
        print("デバッグ: google.generativeai をインポートします。")
        import google.generativeai as genai
        sys.stdout.flush()
        
        print("デバッグ: 環境変数を読み込みます。")
        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY2')
        g_rakuten_app_id = os.getenv('RAKUTEN_APP_ID')
        g_rakuten_affiliate_id = os.getenv('RAKUTEN_AFFILIATE_ID')
        
        if not all([GEMINI_API_KEY, g_rakuten_app_id, g_rakuten_affiliate_id]):
            print("🛑 エラー: 必要なAPIキーが環境変数に設定されていません。")
            return False
            
        print("デバッグ: genai.configure() を実行します。")
        genai.configure(api_key=GEMINI_API_KEY)
        sys.stdout.flush()

        print("デバッグ: GenerativeModel() を初期化します。")
        g_gemini_model = genai.GenerativeModel('gemini-1.5-flash')
        sys.stdout.flush()

        print("✅ APIキーの読み込みとGeminiモデルの準備が完了しました。")
        sys.stdout.flush()
        return True
    except Exception as e:
        print(f"🛑 エラー: APIセットアップ中にエラー: {e}")
        sys.stdout.flush()
        return False

def get_gspread_client():
    print("デバッグ: get_gspread_client() 関数を開始します。")
    sys.stdout.flush()
    try:
        print("デバッグ: gspread と Credentials をインポートします。")
        import gspread
        from google.oauth2.service_account import Credentials
        sys.stdout.flush()

        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            print(f"デバッグ: サービスアカウントファイル '{SERVICE_ACCOUNT_FILE}' が見つかりました。認証を開始します。")
            sys.stdout.flush()
            creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
            gc = gspread.authorize(creds)
            print("✅ gspreadクライアントの認証に成功しました。")
            sys.stdout.flush()
            return gc
        else:
            print(f"🛑 エラー: サービスアカウントのキーファイル '{SERVICE_ACCOUNT_FILE}' が見つかりません。")
            return None
    except Exception as e:
        print(f"🛑 エラー: gspreadクライアントの取得中にエラー: {e}")
        return None

# ==============================================================================
# プログラム１：価値提供ツイート案（フォロワー獲得用）
# ==============================================================================
def run_content_planner():
    print("  - 価値提供ツイート案を生成中...")
    sys.stdout.flush()
    try:
        theme_prompt = f"あなたは日本のSNSマーケティングの専門家です。X(Twitter)アカウント「ゆあ＠プチプラコスメ塾」のフォロワーが保存したくなるような、詳しい解説形式の投稿テーマを1つ考えてください。\n#考慮すべき状況\n- 現在の時期：{datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y年%m月')}\n- 最近の美容トレンド：Y2Kメイク、純欲メイク、中顔面短縮メイクなど\n#出力形式\n- 1行に1つのテーマで出力。番号やハイフンは不要。"
        response = g_gemini_model.generate_content(theme_prompt)
        topic = response.text.strip()
        print(f"  ✅ 生成されたテーマ: {topic}")
        sys.stdout.flush()

        post_prompt = f"あなたは、Xアカウント「ゆあ＠プチプラコスメ塾」の運営者「ゆあ」です。以下のテーマで、読者の興味を引くタイトルから始まる、一つのまとまった読み応えのある解説記事を作成してください。\n# ルール\n- 親しみやすく、少し先生のような頼れる口調で書く。\n- 文字数制限はありません。\n- アスタリスク（*）やシャープ（#）などのマークダウン記法は一切使用しないでください。代わりに【】や・（中黒点）などを使って視覚的に分かりやすくしてください。\n- 箇条書きや絵文字（✨💄💡など）を効果的に使う。\n- 最後にハッシュタグ #プチプラコスメ #コスメ塾 を付ける。\n# 投稿テーマ\n{topic}"
        response = g_gemini_model.generate_content(post_prompt)
        post_content = response.text.strip()
        return {"type": "planner", "topic": topic, "content": post_content}
    except Exception as e:
        print(f"  🛑 価値提供ツイートの生成中にエラー: {e}")
        sys.stdout.flush()
        return None

# ==============================================================================
# プログラム２：アフィリエイト投稿案
# ==============================================================================
def generate_affiliate_post():
    print("  - アフィリエイト投稿案を生成中...")
    sys.stdout.flush()
    try:
        print("    デバッグ: requests をインポートします。")
        import requests
        sys.stdout.flush()

        keyword_prompt = "あなたは楽天市場で化粧品を探しているトレンドに敏感な女性です。「プチプラコスメ」や「韓国コスメ」関連で、具体的な検索キーワードを1つ生成してください。(例: KATE リップモンスター)。回答はキーワード文字列のみでお願いします。"
        response = g_gemini_model.generate_content(keyword_prompt)
        keyword = response.text.strip()
        print(f"  ✅ 生成されたキーワード: {keyword}")
        sys.stdout.flush()

        params = {"applicationId": g_rakuten_app_id, "affiliateId": g_rakuten_affiliate_id, "keyword": keyword, "format": "json", "sort": "-reviewCount", "hits": 5}
        response = requests.get("https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601", params=params)
        response.raise_for_status()
        items = response.json().get("Items", [])
        
        if not items:
            print(f"  ⚠️ 楽天で「{keyword}」に合う商品が見つかりませんでした。")
            return None
            
        formatted_items = "\n".join([f"- 商品名: {i['Item']['itemName']}, キャッチコピー: {i['Item']['catchcopy']}, URL: {i['Item']['affiliateUrl']}" for i in items])
        tweet_prompt = f"あなたは人気のコスメ紹介インフルエンサーです。以下の楽天の人気商品リストから、最も響く商品を1つ選び、その商品の紹介文とアフィリエイトURLをJSON形式で返してください。\n#ルール\n- 価格に触れない\n- 100文字以内\n- #PR #楽天でみつけた神コスメ を含める\n#JSON形式\n{{\"tweet_text\": \"（紹介文）\", \"affiliate_url\": \"（URL）\"}}\n#商品リスト:\n{formatted_items}"
        
        response = g_gemini_model.generate_content(tweet_prompt)
        result = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
        
        short_url_res = requests.get(f"http://tinyurl.com/api-create.php?url={result['affiliate_url']}")
        short_url = short_url_res.text if short_url_res.status_code == 200 else result['affiliate_url']
        
        full_tweet = f"{result['tweet_text']}\n\n👇商品の詳細はこちらからチェック✨\n{short_url}"
        print(f"  ✅ アフィリエイト投稿案を生成完了: {keyword}")
        sys.stdout.flush()
        return {"type": "affiliate", "topic": f"アフィリエイト投稿: {keyword}", "content": full_tweet}
    except Exception as e:
        print(f"  🛑 アフィリエイト投稿の生成中にエラー: {e}")
        sys.stdout.flush()
        return None

# ==============================================================================
# メインの実行ロジック
# ==============================================================================
if __name__ == "__main__":
    print("--- メイン処理の開始 ---")
    sys.stdout.flush()
    
    if not setup_apis():
        raise SystemExit("APIクライアントのセットアップに失敗。")

    gc = get_gspread_client()
    if not gc:
        raise SystemExit("スプレッドシートクライアントのセットアップに失敗。")

    print("✅ 全てのクライアント準備が完了しました。")
    sys.stdout.flush()

    try:
        sh = gc.open(SPREADSHEET_NAME)
        worksheet = sh.sheet1
        worksheet.clear() 
        header = ['生成日時', '種別・テーマ', '投稿内容']
        worksheet.append_row(header)
        print("✅ スプレッドシートの準備完了。")
        sys.stdout.flush()
    except Exception as e:
        print(f"🛑 スプレッドシートの準備中にエラー: {e}"); raise SystemExit()

    jst = pytz.timezone('Asia/Tokyo')
    today_weekday = date.today().weekday()
    schedule = HOLIDAY_SCHEDULE if today_weekday >= 5 else WEEKDAY_SCHEDULE
    planner_count = list(schedule.values()).count("planner")
    affiliate_count = list(schedule.values()).count("affiliate")
    print(f"本日のタスク: フォロワー獲得投稿={planner_count}件, アフィリエイト投稿={affiliate_count}件")
    sys.stdout.flush()

    generated_posts_map = {'planner': [], 'affiliate': []}

    print("\n--- 投稿案の一括生成を開始します ---")
    sys.stdout.flush()
    for _ in range(planner_count):
        post = run_content_planner()
        if post: generated_posts_map['planner'].append(post)
        time.sleep(20)
        
    for _ in range(affiliate_count):
        post = generate_affiliate_post()
        if post: generated_posts_map['affiliate'].append(post)
        time.sleep(20)

    print("\n--- スプレッドシートへの書き込み処理を開始します ---")
    sys.stdout.flush()
    
    rows_to_add = []
    for time_str, task_type in sorted(schedule.items()):
        if generated_posts_map[task_type]:
            post_to_write = generated_posts_map[task_type].pop(0)
            rows_to_add.append([datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S'), post_to_write['topic'], post_to_write['content']])
    
    if rows_to_add:
        worksheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        print(f"✅ スプレッドシートに{len(rows_to_add)}件の投稿案を全て書き込みました。")
        sys.stdout.flush()

    print("🏁 全ての処理が完了しました。")
    sys.stdout.flush()

import os
import random
import json
import requests
import time
import re
from datetime import datetime
import pytz
import gspread
import google.generativeai as genai
from google.oauth2.service_account import Credentials
import tweepy

# --- 定数設定 ---
SPREADSHEET_NAME = 'コスメ投稿案リスト'
SERVICE_ACCOUNT_FILE = 'google_credentials.json'

# --- スケジュール定義 ---
WEEKDAY_SCHEDULE = {
    "07:00": "planner", "07:30": "planner", "08:30": "planner", "12:05": "planner", "12:30": "planner",
    "16:00": "planner", "17:30": "planner", "19:00": "affiliate", "20:00": "affiliate", "21:00": "affiliate",
    "21:45": "planner", "22:15": "affiliate", "23:00": "planner", "23:45": "planner", "00:30": "planner"
}
HOLIDAY_SCHEDULE = {
    "09:30": "planner", "10:30": "planner", "11:30": "affiliate", "13:00": "planner", "14:30": "planner",
    "16:00": "affiliate", "17:30": "planner", "19:00": "planner", "20:00": "affiliate", "21:00": "affiliate",
    "21:45": "planner", "22:30": "affiliate", "23:15": "planner", "23:50": "affiliate", "00:30": "planner"
}

# --- グローバル変数 ---
g_rakuten_app_id = None
g_rakuten_affiliate_id = None
g_x_client_v2 = None
g_x_api_v1 = None

# --- 初期セットアップ ---
def setup_apis():
    global g_rakuten_app_id, g_rakuten_affiliate_id, g_x_client_v2, g_x_api_v1
    try:
        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY2')
        g_rakuten_app_id = os.getenv('RAKUTEN_APP_ID')
        g_rakuten_affiliate_id = os.getenv('RAKUTEN_AFFILIATE_ID')
        genai.configure(api_key=GEMINI_API_KEY)
        
        X_API_KEY = os.getenv('X_API_KEY')
        X_API_SECRET = os.getenv('X_API_SECRET')
        X_ACCESS_TOKEN = os.getenv('X_ACCESS_TOKEN')
        X_ACCESS_TOKEN_SECRET = os.getenv('X_ACCESS_TOKEN_SECRET')
        
        g_x_client_v2 = tweepy.Client(
            consumer_key=X_API_KEY, consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN, access_token_secret=X_ACCESS_TOKEN_SECRET
        )
        auth_v1 = tweepy.OAuth1UserHandler(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET)
        g_x_api_v1 = tweepy.API(auth_v1)

        print("✅ 全てのAPIクライアントの準備が完了しました。")
        return True
    except Exception as e:
        print(f"🛑 エラー: 環境変数からAPIキーを読み込めませんでした。エラー詳細: {e}")
        return False

def get_gspread_client():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        return gspread.authorize(creds)
    return None

# --- X投稿関数 ---
def post_to_x(client, text):
    try:
        response = client.create_tweet(text=text)
        print(f"✅ Xへのテキスト投稿に成功！ Tweet ID: {response.data['id']}")
        return response.data['id']
    except Exception as e:
        print(f"🛑 Xへのテキスト投稿中にエラー: {e}")
        return None

# ==============================================================================
# プログラム１：価値提供ツイート案（フォロワー獲得用）
# ==============================================================================
def run_content_planner(worksheet):
    print("--- プログラム１：価値提供ツイート案の生成を実行します ---")
    try:
        theme_prompt = f"あなたは、日本のSNSマーケティングの専門家です。X(Twitter)アカウント「ゆあ＠プチプラコスメ塾」の投稿テーマを、今度は少し詳しめに解説できるようなものを1つ考えてください。\n# アカウント情報\n- ターゲット：日本の10代〜20代の女性\n- コンセプト：プチプラコスメ専門家「ゆあ」が、塾の先生のようにコスメの選び方やメイク術を教える\n- 目的：フォロワーを増やすこと。特に情報の価値を高め、投稿の保存数を増やしたい\n# 考慮すべき現在の状況\n- 現在の時期：{datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y年%m月')}\n- 季節的な悩み：梅雨の湿気、汗によるメイク崩れ、紫外線対策、夏のトレンドカラーなど\n# 出力形式\n- 1行に1つのテーマで出力してください。番号やハイフンは不要です。"
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(theme_prompt)
        topic = response.text.strip()
        print(f"✅ 生成されたテーマ: {topic}")

        post_prompt = f"あなたは、Xアカウント「ゆあ＠プチプラコスメ塾」の運営者「ゆあ」です。プチプラコスメの専門家として、10代〜20代のフォロワーにメイクの楽しさやコツを教えています。以下のルールを厳守して、「スレッド投稿（複数の投稿が連なる形式）」を作成してください。\n# ルール\n- 親しみやすく、少し先生のような頼れる口調で書く。\n- 2〜3個の投稿で構成されるスレッドを作成する。\n- 【1番目の投稿】は、読者の興味を引く「問題提起」や「結論の予告」で始める。投稿の最後は「続きはリプ欄へ！👇」のように、スレッドが続くことを示す言葉で締める。\n- 【2番目以降の投稿】で、具体的な方法や詳しい解説を行う。絵文字や箇条書きを使い、視覚的に分かりやすくする。\n- 各投稿は、絵文字やハッシュタグを含めて、必ず日本語140文字以内に厳密におさめること。\n- 各投稿の間は、必ず「---」という区切り文字だけを入れてください。\n- ハッシュタグ（#プチプラコスメ #コスメ塾 など）は、スレッドの最後の投稿にまとめて3つ程度入れる。\n# 投稿テーマ\n{topic}"
        response = model.generate_content(post_prompt)
        threaded_posts = [post.strip() for post in response.text.strip().split('---') if post.strip()]
        
        if threaded_posts:
            # スレッド形式で投稿
            last_tweet_id = None
            for i, post_text in enumerate(threaded_posts):
                if i == 0: # 最初のツイート
                    tweet_id = post_to_x(g_x_client_v2, post_text)
                    last_tweet_id = tweet_id
                else: # 返信ツイート
                    if last_tweet_id:
                        tweet_id = g_x_client_v2.create_tweet(text=post_text, in_reply_to_tweet_id=last_tweet_id)
                        last_tweet_id = tweet_id.data['id']
                time.sleep(3)
            
            # スプレッドシートに記録
            jst = pytz.timezone('Asia/Tokyo')
            timestamp = datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')
            row_to_add = [timestamp, topic] + threaded_posts
            worksheet.append_row(row_to_add)
            print(f"✅ 価値提供ツイートを投稿し、スプレッドシートに記録しました。")
    except Exception as e:
        print(f"🛑 価値提供ツイートの処理中にエラー: {e}")

# ==============================================================================
# プログラム２：アフィリエイト投稿案
# ==============================================================================
def run_affiliate_bot(worksheet):
    # この関数の中身は、Colab最終版の記憶機能付きのものをそのまま使います
    print("--- プログラム２：アフィリエイト投稿の生成と投稿を実行します ---")
    
    # 記憶機能のためのヘルパー関数
    def load_posted_ids(filepath):
        if not os.path.exists(filepath): return set()
        with open(filepath, 'r', encoding='utf-8') as f:
            return {line.strip() for line in f if line.strip()}

    def save_posted_id(item_code, filepath):
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(item_code + '\n')
        print(f"✅ 新しい商品IDを記憶しました: {item_code}")

    # キーワード生成のためのヘルパー関数
    def create_dynamic_prompt_for_keyword():
        current_month = datetime.now().month
        if 3 <= current_month <= 5: seasonal_topics = ["春色コスメ", "花粉対策 スキンケア", "UV下地"]
        elif 6 <= current_month <= 8: seasonal_topics = ["汗に強い ファンデーション", "ラメ アイシャドウ", "夏の毛穴ケア"]
        elif 9 <= current_month <= 11: seasonal_topics = ["秋色リップ", "マット アイシャドウ", "保湿美容液"]
        else: seasonal_topics = ["高保湿 クリーム", "クリスマスコフレ", "冬の乾燥肌対策"]
        concern_topics = ["毛穴ケア", "ニキビ跡 コンシーラー", "敏感肌用 化粧水"]
        category_topics = ["新作リップ", "韓国アイシャドウパレット", "バズりコスメ"]
        chosen_topic = random.choice(seasonal_topics + concern_topics + category_topics)
        print(f"✅ Geminiへのお題を生成しました: 『{chosen_topic}』")
        return f"あなたは、楽天市場でこれから化粧品を探そうとしている、トレンドに敏感な日本の10代〜20代の女性です。今回は特に「{chosen_topic}」というテーマで商品を探しています。このテーマに沿って、楽天市場で検索するための、具体的でヒットしやすい検索キーワードを1つだけ生成してください。\n# 指示:\n- 回答は、生成したキーワードの文字列だけにしてください。"

    # メインの実行ロジック
    drive_save_path = "/tmp" # Renderでは/tmpが書き込み可能
    memory_file_path = os.path.join(drive_save_path, "posted_item_ids.txt")
    posted_ids = load_posted_ids(memory_file_path)

    for _ in range(5): # 最大5回リトライ
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = create_dynamic_prompt_for_keyword()
        response = model.generate_content(prompt)
        keyword = response.text.strip()

        sort = random.choice(["standard", "-reviewCount", "-reviewAverage"])
        page = random.randint(1, 5)
        params = {"applicationId": g_rakuten_app_id, "affiliateId": g_rakuten_affiliate_id, "keyword": keyword, "format": "json", "sort": sort, "hits": 30, "page": page}
        response = requests.get("https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601", params=params)
        items = response.json().get("Items", [])
        
        new_items = [item['Item'] for item in items if item['Item']['itemCode'] not in posted_ids]
        
        if new_items:
            # 候補が見つかったので、ツイート生成へ
            items_for_gemini = random.sample(new_items, min(len(new_items), 10))
            formatted_items = "\n".join([f"- 商品名: {i['itemName']}, URL: {i['affiliateUrl']}, itemCode: {i['itemCode']}" for i in items_for_gemini])
            tweet_prompt = f"あなたは人気のコスメを紹介するインフルエンサーです。以下の楽天の商品リストの中から、10代から20代の女性に最もおすすめしたい「最強のプチプラコスメ」を1つだけ選び、その商品の紹介文とアフィリエイトURL、itemCodeをJSON形式で返してください。\n# 制約条件:\n- 「価格」に触れない。\n- 紹介文は100文字以内。\n- ハッシュタグ「#PR」「#プチプラコスメ」を入れる。\n# JSON形式:\n{{\n  \"tweet_text\": \"（紹介文）\",\n  \"affiliate_url\": \"（URL）\",\n  \"itemCode\": \"（itemCode）\"\n}}\n# 商品リスト:\n{formatted_items}"
            
            response = model.generate_content(tweet_prompt)
            result = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
            
            short_url = requests.get(f"http://tinyurl.com/api-create.php?url={result['affiliate_url']}").text
            full_tweet = f"{result['tweet_text']}\n\n👇商品の詳細はこちらからチェック✨\n{short_url}"
            
            if post_to_x(g_x_client_v2, full_tweet):
                jst = pytz.timezone('Asia/Tokyo')
                timestamp = datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')
                row_to_add = [timestamp, f"アフィリエイト投稿: {keyword}", full_tweet, result['itemCode']]
                worksheet.append_row(row_to_add)
                save_posted_id(result['itemCode'], memory_file_path)
                print("✅ アフィリエイト投稿を投稿し、スプレッドシートと記憶ファイルに記録しました。")
            return # 成功したので終了
    print("⚠️ 5回リトライしましたが、新しい商品を見つけられませんでした。")

# ==============================================================================
# メインの実行ロジック
# ==============================================================================
if __name__ == "__main__":
    print("🚀 スケジュール実行を開始します。")
    if not setup_apis():
        raise SystemExit("APIクライアントのセットアップに失敗したため、処理を終了します。")

    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    current_time_str = now.strftime("%H:%M")
    weekday = now.weekday()
    
    print(f"現在の日本時間: {now.strftime('%Y-%m-%d %H:%M:%S')} ({['月','火','水','木','金','土','日'][weekday]}曜日) です。")

    schedule = HOLIDAY_SCHEDULE if weekday >= 5 else WEEKDAY_SCHEDULE
    
    if current_time_str in schedule:
        task = schedule[current_time_str]
        print(f"⏰ スケジュールされた時刻です！タスク「{task}」を実行します。")
        
        gc = get_gspread_client()
        if gc:
            try:
                sh = gc.open(SPREADSHEET_NAME)
                worksheet = sh.sheet1
                if not worksheet.get_all_values():
                    worksheet.append_row(['生成日時', 'テーマ/キーワード', '投稿内容1', '投稿内容2', '投稿内容3', '投稿内容4'])

                if task == "planner":
                    run_content_planner(worksheet)
                elif task == "affiliate":
                    run_affiliate_bot(worksheet)
            except Exception as e:
                print(f"🛑 スプレッドシートの処理中にエラー: {e}")
    else:
        print("現在の時刻は、指定された投稿スケジュールにありません。")

    print("🏁 処理を終了します。")

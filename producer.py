import os
import sys
import random
import json
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

# --- グローバル変数 ---
g_rakuten_app_id = None
g_rakuten_affiliate_id = None
g_gemini_model = None

# --- 初期セットアップ ---
def setup_apis():
    global g_rakuten_app_id, g_rakuten_affiliate_id, g_gemini_model
    try:
        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY2')
        g_rakuten_app_id = os.getenv('RAKUTEN_APP_ID')
        g_rakuten_affiliate_id = os.getenv('RAKUTEN_AFFILIATE_ID')
        genai.configure(api_key=GEMINI_API_KEY)
        g_gemini_model = genai.GenerativeModel('gemini-1.5-flash')
        print("✅ APIキーとGeminiモデルの準備が完了しました。")
        return True
    except Exception as e:
        print(f"🛑 エラー: APIセットアップ中にエラー: {e}")
        return False

def get_gspread_client():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
            return gspread.authorize(creds)
    except Exception as e:
        print(f"🛑 エラー: gspreadクライアントの取得中にエラー: {e}")
    return None

# ==============================================================================
# プログラム１：価値提供ツイート案（フォロワー獲得用）
# ==============================================================================
def run_content_planner():
    print("  - 価値提供ツイート案を生成中...")
    try:
        theme_prompt = f"あなたは日本のSNSマーケティングの専門家です。X(Twitter)アカウント「ゆあ＠プチプラコスメ塾」のフォロワーが保存したくなるような、詳しい解説形式の投稿テーマを1つ考えてください。\n#考慮すべき状況\n- 現在の時期：{datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y年%m月')}\n- 最近の美容トレンド：Y2Kメイク、純欲メイク、中顔面短縮メイクなど\n#出力形式\n- 1行に1つのテーマで出力。番号やハイフンは不要。"
        response = g_gemini_model.generate_content(theme_prompt)
        topic = response.text.strip()
        print(f"  ✅ 生成されたテーマ: {topic}")

        # ★★★★★ プロンプトを大幅にアップグレード ★★★★★
        post_prompt = f"""
あなたは、Xアカウント「ゆあ＠プチプラコスメ塾」の運営者「ゆあ」です。
プチプラコスメの専門家として、10代〜20代のフォロワーに、実践的で価値の高い情報を提供します。
以下のルールを厳守して、1つのまとまった解説記事を作成してください。

# 絶対的なルール
- **スマホでの見やすさを最優先**する。
- **適度な改行や空白行**を効果的に使い、文章が詰まって見えないようにレイアウトする。
- 重要なキーワードは【】で囲むなどして、視覚的に強調する。
- **アスタリスク(*)などのマークダウン記法は一切使用しない**こと。
- 生成した文章は、必ず**最初から最後まで一人の人間（「ゆあ」）が書いたかのような、一貫した自然な日本語**にする。
- 情報の正確性を重視し、根拠のない内容や、意味の通らない文章は絶対に含めない。
- 最後に、**あなた自身で文章を読み返し、不自然な点がないかセルフチェック**を行ってから出力を完了する。
- 親しみやすく、少し先生のような頼れる口調で書く。
- 読者の興味を引く「タイトル」から始める。
- 箇条書きや絵文字（✨💄💡など）を効果的に使う。
- ハッシュタグ（#プチプラコスメ #コスメ塾 など）は、記事の最後にまとめて3〜4個入れる。

# 投稿テーマ
{topic}
"""
        response = g_gemini_model.generate_content(post_prompt)
        post_content = response.text.strip()
        return {"type": "planner", "topic": topic, "content": post_content}
    except Exception as e:
        print(f"  🛑 価値提供ツイートの生成中にエラー: {e}")
        return None

# ==============================================================================
# プログラム２：アフィリエイト投稿案
# ==============================================================================
def generate_affiliate_post():
    print("  - アフィリエイト投稿案を生成中...")
    for attempt in range(3):
        try:
            import requests
            keyword_prompt = "あなたは楽天市場で化粧品を探しているトレンドに敏感な女性です。「プチプラコスメ」や「韓国コスメ」関連で、具体的な検索キーワードを1つ生成してください。(例: KATE リップモンスター)。回答はキーワード文字列のみでお願いします。"
            response = g_gemini_model.generate_content(keyword_prompt)
            keyword = response.text.strip()
            print(f"  - キーワード「{keyword}」で商品を検索します。(試行{attempt + 1}/3)")

            params = {"applicationId": g_rakuten_app_id, "affiliateId": g_rakuten_affiliate_id, "keyword": keyword, "format": "json", "sort": "-reviewCount", "hits": 5}
            response = requests.get("https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601", params=params)
            response.raise_for_status()
            items = response.json().get("Items", [])
            
            if items:
                formatted_items = "\n".join([f"- 商品名: {i['Item']['itemName']}, キャッチコピー: {i['Item']['catchcopy']}, URL: {i['Item']['affiliateUrl']}" for i in items])
                
                # ★★★★★ プロンプトをアップグレード ★★★★★
                tweet_prompt = f"あなたは人気のコスメ紹介インフルエンサーです。以下の楽天の人気商品リストから、最も響く商品を1つ選び、その商品の紹介文とアフィリエイトURLをJSON形式で返してください。\n#ルール\n- まるでユーザーのリアルな口コミを要約したかのような、説得力のある文章を作成する。\n- **生成する文章は、日本語として自然で、意味が明確に伝わるようにすること。**\n- 「価格」に触れない。\n- 100文字以内にまとめる。\n- ハッシュタグ「#PR」「#楽天でみつけた神コスメ」を入れる。\n#JSON形式\n{{\"tweet_text\": \"（紹介文）\", \"affiliate_url\": \"（URL）\"}}\n#商品リスト:\n{formatted_items}"
                
                response = g_gemini_model.generate_content(tweet_prompt)
                result = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
                short_url = requests.get(f"http://tinyurl.com/api-create.php?url={result['affiliate_url']}").text
                full_tweet = f"{result['tweet_text']}\n\n👇商品の詳細はこちらからチェック✨\n{short_url}"
                print(f"  ✅ アフィリエイト投稿案を生成完了: {keyword}")
                return {"type": "affiliate", "topic": f"アフィリエイト投稿: {keyword}", "content": full_tweet}
            else:
                 print(f"  ⚠️ 楽天で「{keyword}」に合う商品が見つかりませんでした。")
        except Exception as e:
            print(f"  🛑 アフィリエイト投稿の生成中に一時的なエラー: {e}")
        
        print("  - 別のキーワードで再試行します...")
        time.sleep(5)
    
    print("  🛑 3回試行しましたが、アフィリエイト投稿の生成に失敗しました。")
    return None

# ==============================================================================
# メインの実行ロジック
# ==============================================================================
if __name__ == "__main__":
    print("🚀 コンテンツ一括生成プログラムを開始します。")
    if not setup_apis():
        raise SystemExit()

    gc = get_gspread_client()
    if not gc:
        raise SystemExit()

    try:
        sh = gc.open(SPREADSHEET_NAME)
        worksheet = sh.sheet1
        worksheet.clear() 
        header = ['scheduled_time', 'post_type', 'content', 'status', 'posted_time', 'posted_tweet_url']
        worksheet.append_row(header)
        print("✅ スプレッドシートを準備しました。")
    except Exception as e:
        print(f"🛑 スプレッドシートの準備中にエラー: {e}"); raise SystemExit()

    jst = pytz.timezone('Asia/Tokyo')
    today_weekday = date.today().weekday()
    schedule = HOLIDAY_SCHEDULE if today_weekday >= 5 else WEEKDAY_SCHEDULE
    planner_count = list(schedule.values()).count("planner")
    affiliate_count = list(schedule.values()).count("affiliate")
    print(f"本日のタスク: フォロワー獲得投稿={planner_count}件, アフィリエイト投稿={affiliate_count}件")

    generated_posts = []
    print("\n--- 価値提供ツイート案の生成 ---")
    for _ in range(planner_count):
        post = run_content_planner()
        if post: generated_posts.append(post)
        time.sleep(20)
        
    print("\n--- アフィリエイト投稿案の生成 ---")
    for _ in range(affiliate_count):
        post = generate_affiliate_post()
        if post: generated_posts.append(post)
        time.sleep(20)
    
    print("\n--- スプレッドシートへの書き込み処理 ---")
    rows_to_add = []
    planner_posts = [p for p in generated_posts if p['type'] == 'planner']
    affiliate_posts = [p for p in generated_posts if p['type'] == 'affiliate']

    for time_str, task_type in sorted(schedule.items()):
        post_to_write = None
        if task_type == 'planner' and planner_posts:
            post_to_write = planner_posts.pop(0)
        elif task_type == 'affiliate' and affiliate_posts:
            post_to_write = affiliate_posts.pop(0)
        
        if post_to_write:
            # スプレッドシートの列に合わせてデータを調整
            rows_to_add.append([time_str, post_to_write['topic'], post_to_write['content'], 'pending', '', ''])
    
    if rows_to_add:
        worksheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        print(f"✅ スプレッドシートに{len(rows_to_add)}件の投稿案を全て書き込みました。")

    print("🏁 コンテンツ一括生成プログラムを終了します。")

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
# 1日の投稿スケジュール（10件）
POSTING_SCHEDULE = {
    "21:00": "hybrid", "22:00": "hybrid", "22:30": "hybrid", "21:30": "hybrid", "14:00": "hybrid",
    "15:00": "hybrid", "12:30": "hybrid", "19:00": "hybrid", "11:00": "hybrid", "00:00": "hybrid"
}
# 投稿タイプの割合（例：価値提供7割、アフィリエイト3割）
TASK_DISTRIBUTION = ["planner"] * 7 + ["affiliate"] * 3

# ★★★★★ 「お題ガチャ」のテーマリスト ★★★★★
SEASONAL_TOPICS = ["春の新作色っぽリップ", "夏の崩れない最強下地", "秋の抜け感ブラウンシャドウ", "冬の高保湿スキンケア", "紫外線対策におすすめの日焼け止め", "汗・皮脂に強いファンデーション"]
CONCERN_TOPICS = ["気になる毛穴の黒ずみ撃退法", "頑固なニキビ跡を隠すコンシーラー術", "敏感肌でも安心な低刺激コスメ", "ブルベ女子に似合う透明感チーク", "イエベ女子のための必勝アイシャドウ"]
TECHNIQUE_TOPICS = ["中顔面を短縮するメイクテクニック", "誰でも簡単！涙袋の作り方", "プロが教える眉毛の整え方", "チークをアイシャドウとして使う裏技", "証明写真で盛れるメイク術"]
ALL_TOPICS_SEED = SEASONAL_TOPICS + CONCERN_TOPICS + TECHNIQUE_TOPICS

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
        chosen_topic_seed = random.choice(ALL_TOPICS_SEED)
        print(f"  ✅ AIへのお題を決定: 『{chosen_topic_seed}』")
        theme_prompt = f"あなたは日本のSNSマーケティングの専門家です。X(Twitter)アカウント「ゆあ＠プチプラコスメ塾」のフォロワーが保存したくなるような投稿を作るため、以下の切り口から、具体的で魅力的な投稿テーマを1つ考えてください。\n# テーマの切り口\n{chosen_topic_seed}\n# 出力形式\nテーマの文字列のみ"
        response = g_gemini_model.generate_content(theme_prompt)
        topic = response.text.strip()
        print(f"  ✅ 生成された最終テーマ: {topic}")

        post_prompt = f"""あなたは、Xアカウント「ゆあ＠プチプラコスメ塾」の運営者「ゆあ」です。以下のルールを厳守し、「{topic}」に関する、1つのまとまった解説記事を作成してください。\n# 絶対的なルール\n- **【最重要】言及するすべての商品名は、実際に日本で販売されている実在の商品でなければなりません。**架空の商品名は絶対に生成しないでください。\n- **推奨する商品は、必ずその文脈に論理的に適合している必要があります。**\n- **「〇〇（商品名）」のような曖昧な表現や、人間が後から編集することを前提とした指示文は絶対に使用しないでください。**\n- 最後に、あなた自身で文章を読み返し、**事実確認を含めた、総合的なセルフチェック**を行ってから出力を完了してください。\n- スマホでの見やすさを最優先し、適度な改行や空白行を効果的に使うこと。\n- アスタリスク(*)などのマークダウン記法は一切使用しないこと。\n- 読者の興味を引く「タイトル」から始めること。\n- ハッシュタグ（#プチプラコスメ #コスメ塾 など）は、記事の最後にまとめて3〜4個入れること。"
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
                tweet_prompt = f"あなたは人気のコスメ紹介インフルエンサーです。以下の楽天の人気商品リストから、最も響く商品を1つ選び、その商品の紹介文とアフィリエイトURLをJSON形式で返してください。\n#ルール\n- まるでユーザーのリアルな口コミを要約したかのような、説得力のある文章を作成する。\n- 日本語として自然で、意味が明確に伝わるようにすること。\n- 「価格」に触れない。\n- 100文字以内。\n- #PR #楽天でみつけた神コスメ を含める。\n#JSON形式\n{{\"tweet_text\": \"（紹介文）\", \"affiliate_url\": \"（URL）\"}}\n#商品リスト:\n{formatted_items}"
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
    if not setup_apis(): raise SystemExit()
    gc = get_gspread_client()
    if not gc: raise SystemExit()

    try:
        sh = gc.open(SPREADSHEET_NAME)
        worksheet = sh.sheet1
        worksheet.clear() 
        header = ['scheduled_time', 'post_type', 'content', 'status', 'posted_time', 'posted_tweet_url']
        worksheet.append_row(header)
        print("✅ スプレッドシートを準備しました。")
    except Exception as e:
        print(f"🛑 スプレッドシートの準備中にエラー: {e}"); raise SystemExit()

    # その日のタスクリストをシャッフルして作成
    daily_tasks = random.sample(TASK_DISTRIBUTION, len(TASK_DISTRIBUTION))
    print(f"本日のタスク配分（シャッフル後）: {daily_tasks}")

    generated_posts = []
    print("\n--- 今日の投稿案を全て生成します ---")
    
    for task_type in daily_tasks:
        if task_type == "planner":
            post = run_content_planner()
        else: # affiliate
            post = generate_affiliate_post()
        
        if post:
            generated_posts.append(post)
        
        # APIのレート制限を避けるため、各タスクの間に少し待機
        time.sleep(20) 
    
    print(f"\n--- スプレッドシートへの書き込み処理 --- ({len(generated_posts)}件)")
    if generated_posts:
        rows_to_add = []
        # スケジュール時刻に沿って書き込む
        for i, time_str in enumerate(sorted(POSTING_SCHEDULE.keys())):
            if i < len(generated_posts):
                post_to_write = generated_posts[i]
                rows_to_add.append([time_str, post_to_write.get('topic', post_to_write.get('type')), post_to_write['content'], 'pending', '', ''])
        
        if rows_to_add:
            worksheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
            print(f"✅ スプレッドシートに{len(rows_to_add)}件の投稿案を全て書き込みました。")

    print("🏁 コンテンツ一括生成プログラムを終了します。")

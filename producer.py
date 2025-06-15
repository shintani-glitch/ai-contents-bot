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
POSTING_SCHEDULE = {
    "21:00": "hybrid", "22:00": "hybrid", "22:30": "hybrid", "21:30": "hybrid", "14:00": "hybrid",
    "15:00": "hybrid", "12:30": "hybrid", "19:00": "hybrid", "11:00": "hybrid", "00:00": "hybrid"
}
SEASONAL_TOPICS = ["春の新作色っぽリップ", "夏の崩れない最強下地", "秋の抜け感ブラウンシャドウ", "冬の高保湿スキンケア", "紫外線対策 日焼け止め", "汗・皮脂に強いファンデーション"]
CONCERN_TOPICS = ["気になる毛穴の黒ずみ撃退法", "頑固なニキビ跡を隠すコンシーラー術", "敏感肌でも安心な低刺激コスメ", "ブルベ女子に似合う透明感チーク", "イエベ女子のための必勝アイシャドウ"]
TECHNIQUE_TOPICS = ["中顔面を短縮するメイクテクニック", "誰でも簡単！涙袋の作り方", "プロが教える眉毛の整え方", "チークをアイシャドウとして使う裏技", "証明写真 盛れるメイク術"]
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

def search_rakuten(keyword):
    """楽天APIで商品を検索するヘルパー関数"""
    print(f"  - 楽天を検索中... (キーワード: '{keyword}')")
    params = {
        "applicationId": g_rakuten_app_id, "affiliateId": g_rakuten_affiliate_id,
        "keyword": keyword, "format": "json", "sort": random.choice(["standard", "-reviewCount"]),
        "hits": 10, "page": random.randint(1, 3)
    }
    response = requests.get("https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601", params=params)
    response.raise_for_status()
    return response.json().get("Items", [])

# ==============================================================================
# ハイブリッド投稿案を生成するメイン関数
# ==============================================================================
def generate_hybrid_post(topic_seed):
    print(f"  - テーマの切り口「{topic_seed}」で投稿案を生成中...")
    try:
        model = g_gemini_model
        
        # STEP 1: テーマの決定
        theme_prompt = f"あなたは日本のSNSマーケティングの専門家です。X(Twitter)アカウント「ゆあ＠プチプラコスメ塾」のフォロワーが保存したくなるような投稿を作るため、以下の切り口から、具体的で魅力的な投稿テーマを1つ考えてください。\n# テーマの切り口\n{topic_seed}\n# 出力形式\nテーマの文字列のみ"
        response = model.generate_content(theme_prompt)
        topic = response.text.strip()
        print(f"  ✅ 生成された最終テーマ: {topic}")

        # STEP 2: 検索キーワードの生成
        keyword_prompt = f"以下の投稿テーマに最も関連性が高く、楽天市場で商品を検索するための具体的な検索キーワードを1つ生成してください。\n# 投稿テーマ\n{topic}\n# 指示\n- 楽天市場の商品名に含まれやすい、2〜3個の名詞の組み合わせにすること。\n- 回答はキーワード文字列のみ。"
        response = model.generate_content(keyword_prompt)
        smart_keyword = response.text.strip().replace("　", " ")
        print(f"  ✅ AIが考案した「スマートキーワード」: {smart_keyword}")

        # ★★★★★ ここからが2段構えの検索ロジック ★★★★★
        # STEP 3: スマートキーワードでまず検索
        items = search_rakuten(smart_keyword)

        # STEP 4: もし見つからなければ、セーフキーワードで再検索
        if not items:
            print(f"  ⚠️ スマートキーワードで商品が見つかりませんでした。安全なキーワードで再検索します。")
            safe_keyword_prompt = f"以下の文章から、商品を検索するための最も重要で基本的な名詞を2つか3つ、スペース区切りで抜き出してください。\n# 文章\n{topic}"
            response = model.generate_content(safe_keyword_prompt)
            safe_keyword = response.text.strip().replace("　", " ")
            print(f"  ✅ AIが考案した「セーフキーワード」: {safe_keyword}")
            items = search_rakuten(safe_keyword)

        if not items:
            print("  🛑 2回の検索でも関連商品を見つけられませんでした。このテーマをスキップします。")
            return None
        # ★★★★★ ここまでが2段構えの検索ロジック ★★★★★
        
        print(f"  ✅ 楽天で{len(items)}件の商品を発見。")
        item_candidates = random.sample(items, min(len(items), 5))
        formatted_items_string = "\n".join([f"- 商品名: {i['Item']['itemName']}, URL: {i['Item']['affiliateUrl']}" for i in item_candidates])
        
        # STEP 5: 最終的な記事を執筆
        final_post_prompt = f"""あなたはXアカウント「ゆあ＠プチプラコスメ塾」の運営者「ゆあ」です。以下のテーマと商品リストを基に、フォロワーに価値を提供しつつ、自然に商品を紹介する、1つのまとまった投稿を作成してください。\n# 絶対的なルール\n- 1つの投稿として、日本語で合計500文字以内に収めること。\n- **【最重要】投稿の超導入部分（最初の100文字以内）で**、テーマに関する読者の悩みを提示し、その解決策となる商品を「結論」として先に提示し、アフィリエイトURLを記載すること。\n- 投稿の後半では、紹介した商品のさらに詳しい使い方や、関連する美容テクニックなどを解説し、記事全体の価値を高めること。\n- 最後に、投稿内容に最も関連性が高く、インプレッションを最大化できるハッシュタグを5〜6個厳選して付ける。`#PR`も必ず含めること。\n- 必ず具体的な商品名を記述し、「〇〇」のようなプレースホルダーは使わないこと。\n- あなた自身で文章を読み返し、不自然な点がないかセルフチェックしてから出力を完了する。\n# 投稿テーマ\n{topic}\n# 紹介して良い商品リスト（この中から1つだけ選ぶ）\n{formatted_items_string}\n# 出力形式（JSON）\n{{\"content\": \"（生成した500字以内の投稿文全体）\"}}"""
        
        response = model.generate_content(final_post_prompt)
        result = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
        
        long_url_match = re.search(r'(https?://[^\s]+)', result['content'])
        if long_url_match:
            long_url = long_url_match.group(1)
            short_url = requests.get(f"http://tinyurl.com/api-create.php?url={long_url}").text
            final_content = result['content'].replace(long_url, short_url)
        else:
            final_content = result['content']
            
        print(f"  ✅ ハイブリッド投稿案を生成完了。")
        return {"type": "hybrid", "topic": topic, "content": final_content}
        
    except Exception as e:
        print(f"  🛑 ハイブリッド投稿の生成中にエラー: {e}")
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

    rows_to_add = []
    used_topics = set()
    
    # ★★★★★ 投稿数が目標に達するまで挑戦するループ ★★★★★
    target_post_count = len(POSTING_SCHEDULE)
    print(f"\n--- 今日の投稿案 {target_post_count}件の生成を開始します ---")
    
    while len(rows_to_add) < target_post_count:
        print(f"\n--- {len(rows_to_add) + 1}件目の投稿案を生成します ---")
        
        if not list(set(ALL_TOPICS_SEED) - used_topics): # 全てのお題を使い切ったらリセット
            used_topics = set()
        
        available_topics = list(set(ALL_TOPICS_SEED) - used_topics)
        topic_seed = random.choice(available_topics)
        used_topics.add(topic_seed)
        
        post_data = generate_hybrid_post(topic_seed)
        if post_data:
            rows_to_add.append(post_data) # あとで時刻と合わせて書き込む
        
        time.sleep(20)
    
    # スケジュール時刻と生成済み投稿をマッピングして書き込み
    rows_for_sheet = []
    for i, time_str in enumerate(sorted(POSTING_SCHEDULE.keys())):
        if i < len(rows_to_add):
            post = rows_to_add[i]
            rows_for_sheet.append([time_str, post['topic'], post['content'], 'pending', '', ''])
            
    if rows_for_sheet:
        worksheet.append_rows(rows_for_sheet, value_input_option='USER_ENTERED')
        print(f"\n✅ スプレッドシートに{len(rows_for_sheet)}件の投稿案を全て書き込みました。")

    print("🏁 コンテンツ一括生成プログラムを終了します。")

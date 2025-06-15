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

# 発想の種となる「お題」のリスト
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
# 統合されたハイブリッド投稿案を生成するメイン関数
# ==============================================================================
def generate_hybrid_post(topic_seed):
    print(f"  - テーマの切り口「{topic_seed}」で投稿案を生成中...")
    try:
        # STEP 1: テーマの決定
        theme_prompt = f"あなたは日本のSNSマーケティングの専門家です。X(Twitter)アカウント「ゆあ＠プチプラコスメ塾」のフォロワーが保存したくなるような投稿を作るため、以下の切り口から、具体的で魅力的な投稿テーマを1つ考えてください。\n# テーマの切り口\n{topic_seed}\n# 出力形式\nテーマの文字列のみ"
        response = g_gemini_model.generate_content(theme_prompt)
        topic = response.text.strip()
        print(f"  ✅ 生成された最終テーマ: {topic}")

        # STEP 2: 楽天で検索するためのキーワードを生成
        keyword_prompt = f"以下の投稿テーマに最も関連性の高い、楽天市場で商品を検索するための具体的な検索キーワードを1つ生成してください。\n# 投稿テーマ\n{topic}\n# 指示\n- ブランド名や具体的な商品カテゴリ名を含めること。\n- 回答はキーワード文字列のみ。"
        response = g_gemini_model.generate_content(keyword_prompt)
        keyword = response.text.strip()
        print(f"  ✅ 楽天検索用キーワード: {keyword}")

        # STEP 3: 楽天で商品を検索（リトライ機能付き）
        items = []
        for attempt in range(3):
            sort_options = ["standard", "-reviewCount", "-reviewAverage"]
            params = {
                "applicationId": g_rakuten_app_id, "affiliateId": g_rakuten_affiliate_id,
                "keyword": keyword, "format": "json", "sort": random.choice(sort_options),
                "hits": 10, "page": random.randint(1, 3)
            }
            response = requests.get("https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601", params=params)
            response.raise_for_status()
            items = response.json().get("Items", [])
            if items:
                print(f"  ✅ 楽天で{len(items)}件の商品を発見。")
                break
            else:
                print(f"  ⚠️ 楽天で「{keyword}」に合う商品が見つかりませんでした。(試行 {attempt + 1}/3)")
                time.sleep(3)
        
        if not items:
            print("  🛑 3回試行しましたが、関連商品を見つけられませんでした。")
            return None

        # STEP 4: 最終的な記事を執筆
        item_candidates = random.sample(items, min(len(items), 5))
        formatted_items_string = "\n".join([f"- 商品名: {i['Item']['itemName']}, URL: {i['Item']['affiliateUrl']}" for i in item_candidates])
        
        final_post_prompt = f"""
あなたはXアカウント「ゆあ＠プチプラコスメ塾」の運営者「ゆあ」です。
以下のテーマと商品リストを基に、フォロワーに価値を提供しつつ、自然に商品を紹介する、1つのまとまった投稿を作成してください。

# 絶対的なルール
- 1つの投稿として、日本語で400文字以内に収めること。
- 投稿テーマについての詳しい解説やテクニックを先に書き、その流れで**商品リストの中から最もテーマに合う商品を1つだけ選び**、自然な形で紹介する。
- スマホでの見やすさを最優先し、適度な改行、空白行、絵文字（✨💄💡など）を効果的に使う。
- 最後に、投稿内容に最も関連性が高く、インプレッションを最大化できるハッシュタグを3〜4個厳選して付ける。`#PR`も必ず含めること。
- 「〇〇（商品名）」のようなプレースホルダーは絶対に使わず、必ず具体的な商品名を記述する。
- あなた自身で文章を読み返し、不自然な点がないかセルフチェックしてから出力を完了する。

# 投稿テーマ
{topic}

# 紹介して良い商品リスト（この中から1つだけ選ぶ）
{formatted_items_string}

# 出力形式（JSON）
{{
  "content": "（生成した400字以内の投稿文全体。アフィリエイトURLもこの中に含める）"
}}
"""
        response = g_gemini_model.generate_content(final_post_prompt)
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

    # その日のスケジュールで必要な投稿案を生成
    rows_to_add = []
    used_topics = set()
    
    for time_str, task_type in sorted(POSTING_SCHEDULE.items()):
        print(f"\n--- {time_str} ({task_type}) の投稿案を生成します ---")
        
        # 毎回異なる「発想の種」を選ぶ
        topic_seed = ""
        for _ in range(5): # 重複しないトピックを5回まで探す
            topic_seed = random.choice(ALL_TOPICS_SEED)
            if topic_seed not in used_topics:
                used_topics.add(topic_seed)
                break
        
        post_data = generate_hybrid_post(topic_seed)
        if post_data:
            rows_to_add.append([time_str, post_data['topic'], post_data['content'], 'pending', '', ''])
        
        time.sleep(20) # API制限対策
    
    if rows_to_add:
        worksheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        print(f"\n✅ スプレッドシートに{len(rows_to_add)}件の投稿案を全て書き込みました。")

    print("🏁 コンテンツ一括生成プログラムを終了します。")

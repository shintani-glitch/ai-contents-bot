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
SEASONAL_TOPICS = ["春の新作リップ", "夏の崩れない最強下地", "秋の抜け感ブラウンシャドウ", "冬の高保湿スキンケア", "紫外線対策 日焼け止め", "汗・皮脂に強いファンデーション"]
CONCERN_TOPICS = ["毛穴の黒ずみケア", "ニキビ跡 コンシーラー", "敏感肌用 スキンケア", "ブルベ向け 透明感チーク", "イエベ向け アイシャドウ"]
TECHNIQUE_TOPICS = ["中顔面短縮メイク", "涙袋メイク やり方", "プロ級 眉毛の整え方", "チーク アイシャドウ 活用術", "証明写真 盛れるメイク"]
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
# ハイブリッド投稿案を生成するメイン関数
# ==============================================================================
def generate_hybrid_post(topic_seed):
    print(f"  - テーマの切り口「{topic_seed}」で投稿案を生成中...")
    try:
        model = g_gemini_model
        
        theme_prompt = f"あなたは日本のSNSマーケターです。以下の「切り口」から、具体的で魅力的な投稿テーマを1つ考えてください。\n# テーマの切り口\n{topic_seed}\n# 出力形式\nテーマの文字列のみ"
        response = model.generate_content(theme_prompt)
        topic = response.text.strip()
        print(f"  ✅ 生成された最終テーマ: {topic}")

        # ★★★★★ キーワード生成プロンプトを改善 ★★★★★
        keyword_prompt = f"以下の投稿テーマに最も関連性が高く、楽天市場で商品を検索するための具体的な検索キーワードを1つ生成してください。\n# 投稿テーマ\n{topic}\n# 指示\n- 楽天市場の商品名に含まれやすい、2〜3個の名詞の組み合わせにすること。\n- 「おすすめ」「やり方」などの文章的な表現は避けること。\n- （良い例：「セザンヌ チーク ラベンダー」, 悪い例：「透明感が出るラベンダー色のチーク」）\n- 回答はキーワード文字列のみ。"
        response = model.generate_content(keyword_prompt)
        keyword = response.text.strip().replace("　", " ") # 全角スペースを半角に
        print(f"  ✅ 楽天検索用キーワード: {keyword}")

        params = {"applicationId": g_rakuten_app_id, "affiliateId": g_rakuten_affiliate_id, "keyword": keyword, "format": "json", "sort": "-reviewCount", "hits": 5}
        response = requests.get("https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601", params=params)
        response.raise_for_status()
        items = response.json().get("Items", [])
        
        if not items:
            print(f"  ⚠️ 楽天で「{keyword}」に合う商品が見つかりませんでした。")
            return None

        print(f"  ✅ 楽天で{len(items)}件の商品を発見。")
        formatted_items_string = "\n".join([f"- 商品名: {i['Item']['itemName']}, URL: {i['Item']['affiliateUrl']}" for i in items])
        final_post_prompt = f"""あなたはXアカウント「ゆあ＠プチプラコスメ塾」の運営者「ゆあ」です。以下のテーマと商品リストを基に、フォロワーに価値を提供しつつ、自然に商品を紹介する、1つのまとまった投稿を作成してください。\n# 絶対的なルール\n- 1つの投稿として、日本語で400文字以内に収めること。\n- 投稿テーマについての詳しい解説やテクニックを先に書き、その流れで商品リストの中から最もテーマに合う商品を1つだけ選び、自然な形で紹介する。\n- スマホでの見やすさを最優先し、適度な改行、空白行、絵文字（✨💄💡など）を効果的に使う。\n- 最後に、投稿内容に最も関連性が高く、インプレッションを最大化できるハッシュタグを3〜4個厳選して付ける。`#PR`も必ず含めること。\n- 必ず具体的な商品名を記述し、「〇〇」のようなプレースホルダーは使わない。\n- あなた自身で文章を読み返し、不自然な点がないかセルフチェックしてから出力を完了する。\n# 投稿テーマ\n{topic}\n# 紹介して良い商品リスト（この中から1つだけ選ぶ）\n{formatted_items_string}\n# 出力形式（JSON）\n{{\"content\": \"（生成した400字以内の投稿文全体。アフィリエイトURLもこの中に含める）\"}}"
        
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

    # ★★★★★ 投稿案が必要な数だけ揃うまで再挑戦するループに変更 ★★★★★
    generated_posts = []
    used_topics = set()
    
    print(f"\n--- 今日の投稿案 {len(POSTING_SCHEDULE)}件の生成を開始します ---")
    
    while len(generated_posts) < len(POSTING_SCHEDULE):
        print(f"\n--- {len(generated_posts) + 1}件目の投稿案を生成します ---")
        
        topic_seed = ""
        # まだ使っていない「発想の種」を選ぶ
        available_topics = list(set(ALL_TOPICS_SEED) - used_topics)
        if not available_topics: # もし全てのお題を使い切ったらリセット
            used_topics = set()
            available_topics = ALL_TOPICS_SEED
        topic_seed = random.choice(available_topics)
        used_topics.add(topic_seed)
        
        post_data = generate_hybrid_post(topic_seed)
        if post_data:
            generated_posts.append(post_data)
        
        # APIのレート制限を避けるため、各タスクの間に少し待機
        time.sleep(20)
    
    print(f"\n--- スプレッドシートへの書き込み処理 --- ({len(generated_posts)}件)")
    if generated_posts:
        rows_to_add = []
        # スケジュール時刻に沿って書き込む
        for i, time_str in enumerate(sorted(POSTING_SCHEDULE.keys())):
            if i < len(generated_posts):
                post_to_write = generated_posts[i]
                rows_to_add.append([time_str, post_to_write['topic'], post_to_write['content'], 'pending', '', ''])
        
        if rows_to_add:
            worksheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
            print(f"✅ スプレッドシートに{len(rows_to_add)}件の投稿案を全て書き込みました。")

    print("🏁 コンテンツ一括生成プログラムを終了します。")

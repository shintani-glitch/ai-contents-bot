import os
import sys
import random
import json
import time
import re
from datetime import datetime, date
import pytz

# --- 最初に最低限のライブラリのみをインポート ---
print("--- SCRIPT START ---")
sys.stdout.flush()

# --- 定数と設定 ---
SPREADSHEET_NAME = 'コスメ投稿案リスト'
SERVICE_ACCOUNT_FILE = 'google_credentials.json'
POSTING_SCHEDULE = {
    "21:00": "hybrid", "22:00": "hybrid", "22:30": "hybrid", "21:30": "hybrid", "14:00": "hybrid",
    "15:00": "hybrid", "12:30": "hybrid", "19:00": "hybrid", "11:00": "hybrid", "00:00": "hybrid"
}

# --- グローバル変数 ---
g_gemini_model = None
g_rakuten_app_id, g_rakuten_affiliate_id = None, None
g_amazon_access_key, g_amazon_secret_key, g_amazon_associate_tag = None, None, None

# --- 初期セットアップ ---
def setup_apis():
    global g_rakuten_app_id, g_rakuten_affiliate_id, g_amazon_access_key, g_amazon_secret_key, g_amazon_associate_tag, g_gemini_model
    try:
        import google.generativeai as genai
        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY2')
        g_rakuten_app_id = os.getenv('RAKUTEN_APP_ID')
        g_rakuten_affiliate_id = os.getenv('RAKUTEN_AFFILIATE_ID')
        g_amazon_access_key = os.getenv('AMAZON_ACCESS_KEY')
        g_amazon_secret_key = os.getenv('AMAZON_SECRET_KEY')
        g_amazon_associate_tag = os.getenv('AMAZON_ASSOCIATE_TAG')
        
        if not all([GEMINI_API_KEY, g_rakuten_app_id, g_amazon_access_key]):
            print("🛑 エラー: 必要なAPIキーが環境変数に設定されていません。")
            return False
            
        genai.configure(api_key=GEMINI_API_KEY)
        g_gemini_model = genai.GenerativeModel('gemini-1.5-flash')
        print("✅ 全てのAPIキーを読み込み、モデルを準備しました。")
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

def search_products(platform, keyword):
    print(f"  - {platform.capitalize()}を検索中... (キーワード: '{keyword}')")
    try:
        import requests
        if platform == "rakuten":
            params = {"applicationId": g_rakuten_app_id, "affiliateId": g_rakuten_affiliate_id, "keyword": keyword, "format": "json", "sort": "-reviewCount", "hits": 10}
            response = requests.get("https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601", params=params)
            response.raise_for_status()
            return [{"name": i['Item']['itemName'], "url": i['Item']['affiliateUrl']} for i in response.json().get("Items", [])]
        elif platform == "amazon":
            from paapi5_python_sdk.api.default_api import DefaultApi
            from paapi5_python_sdk.models.partner_type import PartnerType
            from paapi5_python_sdk.models.search_items_request import SearchItemsRequest
            from paapi5_python_sdk.models.search_items_resource import SearchItemsResource
            from paapi5_python_sdk.rest import ApiException
            api_client = DefaultApi(access_key=g_amazon_access_key, secret_key=g_amazon_secret_key, host="webservices.amazon.co.jp", region="us-west-2")
            search_request = SearchItemsRequest(partner_tag=g_amazon_associate_tag, partner_type=PartnerType.ASSOCIATES, keywords=keyword, search_index="Beauty", resources=[SearchItemsResource.ITEMINFO_TITLE, SearchItemsResource.DETAILPAGEURL], item_count=10)
            response = api_client.search_items(search_request)
            return [{"name": i.item_info.title.display_value, "url": i.detail_page_url} for i in response.search_result.items] if response.search_result and response.search_result.items else []
    except Exception as e:
        print(f"  🛑 {platform.capitalize()} APIエラー: {e}")
    return []

def generate_hybrid_post(platform, topic):
    print(f"  - 【{platform.upper()}】のテーマ「{topic}」で投稿案を生成中...")
    try:
        model = g_gemini_model
        keyword_prompt = f"テーマ「{topic}」に最も関連する、ECサイトでヒットしやすい具体的な検索キーワードを1つ生成してください。"
        keyword = model.generate_content(keyword_prompt).text.strip().replace("　", " ")
        
        items = search_products(platform, keyword)
        if not items:
            print(f"  ⚠️ {platform}で商品が見つかりませんでした。")
            return None
            
        formatted_items = "\n".join([f"- 商品名: {i['name']}, URL: {i['url']}" for i in items[:5]])
        platform_name = "楽天市場" if platform == "rakuten" else "Amazon"
        platform_hashtag = "#楽天でみつけた神コスメ" if platform == "rakuten" else "#Amazonで見つけた"
        final_post_prompt = f"あなたはXアカウント「ゆあ＠プチプラコスメ塾」の運営者です。テーマ「{topic}」と{platform_name}の商品リストを基に、価値を提供しつつ自然に商品を1つ紹介する400字以内の投稿をJSON形式で作成してください。\n#ルール\n- 冒頭100文字以内で結論として商品を紹介しURLを記載\n- 最後にハッシュタグを5-6個付けること(#PRと{platform_hashtag}は必須)\n- 具体的な商品名を記述すること\n#商品リスト\n{formatted_items}\n#出力形式\n{{\"content\": \"（投稿文全体）\"}}"
        
        response = model.generate_content(final_post_prompt)
        result = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
        
        long_url_match = re.search(r'(https?://[^\s]+)', result['content'])
        if long_url_match:
            long_url = long_url_match.group(1)
            short_url = requests.get(f"http://tinyurl.com/api-create.php?url={long_url}").text
            final_content = result['content'].replace(long_url, short_url)
        else:
            final_content = result['content']
            
        print(f"  ✅ {platform.capitalize()}の投稿案を生成完了。")
        return {"type": f"{platform}_hybrid", "topic": f"{platform.capitalize()}投稿: {topic}", "content": final_content}
    except Exception as e:
        print(f"  🛑 ハイブリッド投稿の生成中にエラー: {e}")
        return None

if __name__ == "__main__":
    print("--- メイン処理の開始 ---")
    sys.stdout.flush()
    if not setup_apis(): raise SystemExit()
    
    gc = get_gspread_client()
    if not gc: raise SystemExit()

    print("✅ 全てのクライアント準備が完了しました。")
    sys.stdout.flush()

    try:
        sh = gc.open(SPREADSHEET_NAME)
        worksheet = sh.sheet1
        worksheet.clear() 
        header = ['scheduled_time', 'post_type', 'content', 'status', 'posted_time', 'posted_tweet_url']
        worksheet.append_row(header)
        print("✅ スプレッドシートを準備しました。")
        sys.stdout.flush()
    except Exception as e:
        print(f"🛑 スプレッドシートの準備中にエラー: {e}"); raise SystemExit()

    rows_to_add = []
    print(f"\n--- 今日の投稿案 {len(POSTING_SCHEDULE)}件の生成を開始します ---")
    sys.stdout.flush()
    
    for i, time_str in enumerate(sorted(POSTING_SCHEDULE.keys())):
        platform_to_use = "rakuten" if i % 2 == 0 else "amazon"
        print(f"\n--- {time_str} ({platform_to_use.upper()}) の投稿案を生成します ---")
        sys.stdout.flush()
        
        post_data = generate_hybrid_post(platform_to_use, "コスメ") # topicは固定または動的に
        if post_data:
            rows_to_add.append([time_str, post_data['topic'], post_data['content'], 'pending', '', ''])
        
        time.sleep(30)
    
    if rows_to_add:
        worksheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        print(f"\n✅ スプレッドシートに{len(rows_to_add)}件の投稿案を全て書き込みました。")
        sys.stdout.flush()

    print("🏁 コンテンツ一括生成プログラムを終了します。")
    sys.stdout.flush()

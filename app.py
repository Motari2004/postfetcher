import requests
import json
import os
from datetime import datetime, timedelta

# Your API token
API_TOKEN = "5ae60cb46979c92bc6454e41ff94ab44a6ffb2d9fca6f4c7afa30fcaf7d05a47"

# Cache file
CACHE_FILE = "posts_cache.json"

def format_number(value):
    """Safely format numbers even if they're strings like '2.2K'"""
    if value is None:
        return "0"
    if isinstance(value, (int, float)):
        return f"{value:,}"
    if isinstance(value, str):
        value = value.replace(',', '')
        if 'K' in value and value.replace('K', '').replace('.', '').isdigit():
            try:
                num = float(value.replace('K', '')) * 1000
                return f"{int(num):,}"
            except:
                return value
        elif 'M' in value and value.replace('M', '').replace('.', '').isdigit():
            try:
                num = float(value.replace('M', '')) * 1000000
                return f"{int(num):,}"
            except:
                return value
        elif value.replace('.', '').isdigit():
            try:
                return f"{int(float(value)):,}"
            except:
                return value
        else:
            return value
    return str(value)

def extract_image_urls(post):
    """Extract image URLs from a post"""
    image_urls = []
    values = post.get("values", {})
    
    # Check for photo_image
    photo_image = values.get("photo_image")
    if photo_image:
        image_urls.append(photo_image)
    
    # Check for media in details
    details = post.get("details", {})
    media = details.get("media", [])
    if media and isinstance(media, list):
        for item in media:
            if isinstance(item, dict):
                for field in ['image', 'url', 'src', 'thumbnail', 'preview']:
                    if field in item and item[field]:
                        image_urls.append(item[field])
    
    # Look for image URLs in the post data
    import re
    post_str = json.dumps(post)
    cdn_patterns = [
        r'https://[^"]*\.fbcdn\.net[^"]*\.(?:jpg|png|jpeg|gif|webp)',
        r'https://[^"]*\.cdn\.facebook\.net[^"]*\.(?:jpg|png|jpeg|gif|webp)',
        r'https://[^"]*\.(?:jpg|png|jpeg|gif|webp)[^"]*'
    ]
    
    for pattern in cdn_patterns:
        matches = re.findall(pattern, post_str, re.IGNORECASE)
        image_urls.extend(matches)
    
    # Remove duplicates
    image_urls = list(dict.fromkeys(image_urls))
    return image_urls

def get_cached_posts():
    """Check if we have cached posts"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
        # Check if cache is less than 24 hours old
        cache_time = datetime.fromisoformat(cache["timestamp"])
        if datetime.now() - cache_time < timedelta(hours=24):
            return cache["posts"]
    return None

def save_to_cache(posts):
    """Save posts to cache"""
    cache = {
        "timestamp": datetime.now().isoformat(),
        "posts": posts
    }
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def get_bbc_posts(force_refresh=False):
    """Get latest posts from BBC News with caching"""
    
    # Check cache first
    if not force_refresh:
        cached = get_cached_posts()
        if cached:
            print(f"📦 Using cached posts (last fetched: {datetime.now().strftime('%H:%M:%S')})")
            print("💡 To force refresh, use: python app.py --refresh")
            return cached
    
    print("📰 Fetching fresh posts from API...")
    
    url = "https://api.socialapis.io/facebook/pages/posts"
    headers = {"x-api-token": API_TOKEN}
    params = {
        "link": "https://www.facebook.com/bbcnews",
        "limit": 3
    }
    
    print("=" * 70)
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        
        # Track credits
        meta = data.get('meta', {})
        print(f"💳 Credits used: {meta.get('creditsCharged', 0)}")
        print(f"💳 Credits remaining: {meta.get('creditsRemaining', 0)}")
        print("=" * 70)
        
        # Extract posts
        posts_data = data.get("data", {})
        posts = posts_data.get("posts", [])
        
        if not posts:
            print("❌ No posts found.")
            return []
        
        # Save to cache
        save_to_cache(posts)
        print(f"✅ Saved {len(posts)} posts to cache")
        
        return posts
        
    else:
        print(f"❌ Error {response.status_code}: {response.text}")
        return []

def display_posts(posts):
    """Display posts in a readable format"""
    if not posts:
        return
    
    print(f"\n📰 Found {len(posts)} posts\n")
    
    for i, post in enumerate(posts, 1):
        details = post.get("details", {})
        values = post.get("values", {})
        reactions = post.get("reactions", {})
        
        # Get text
        text = values.get("text", "No text")
        
        # Get time
        publish_time = values.get("publish_time", "N/A")
        if publish_time and publish_time != "N/A":
            try:
                if 'T' in str(publish_time):
                    dt = datetime.fromisoformat(str(publish_time).replace('Z', '+00:00'))
                    publish_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
        
        # Get post ID
        post_id = details.get("post_id", "N/A")
        
        # Get media type
        media_type = values.get("is_media")
        
        # Get reactions
        total_reactions = reactions.get("total_reaction_count", 0)
        
        print(f"📌 POST #{i}")
        print(f"📝 {text}")
        print(f"🕐 {publish_time}")
        print(f"🔗 Post ID: {post_id}")
        
        if media_type:
            print(f"📎 Media: {media_type}")
        
        # Extract and display image URLs
        image_urls = extract_image_urls(post)
        if image_urls:
            print(f"\n🖼️ Images ({len(image_urls)}):")
            for idx, img_url in enumerate(image_urls[:3], 1):
                print(f"   {idx}. {img_url[:100]}...")
        
        # Show reactions
        if total_reactions > 0:
            print(f"\n❤️ Reactions:")
            for reaction, count in reactions.items():
                if reaction != "total_reaction_count" and count > 0:
                    print(f"   {reaction}: {count:,}")
        
        # Get comments and shares
        comments = details.get("comments_count", "0")
        shares = details.get("share_count", "0")
        
        print(f"\n💬 Comments: {format_number(comments)}")
        print(f"🔄 Shares: {format_number(shares)}")
        
        # Get post link
        post_link = details.get("post_link")
        if post_link:
            print(f"🔗 Link: {post_link}")
        
        print("-" * 70)

if __name__ == "__main__":
    import sys
    
    # Check for refresh flag
    force_refresh = "--refresh" in sys.argv
    
    posts = get_bbc_posts(force_refresh=force_refresh)
    display_posts(posts)
    
    print("\n✅ Done!")
    print(f"📊 Total requests used this session: {1 if not force_refresh and get_cached_posts() else 1}")
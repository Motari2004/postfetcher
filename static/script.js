let currentPosts = [];

async function fetchPosts(forceRefresh = false) {
    const pageUrl = document.getElementById('pageUrl').value.trim();
    const postCount = parseInt(document.getElementById('postCount').value);
    
    if (!pageUrl) {
        alert('Please enter a Facebook page URL');
        return;
    }
    
    const loading = document.getElementById('loading');
    const results = document.getElementById('results');
    const fetchBtn = document.getElementById('fetchBtn');
    const refreshBtn = document.getElementById('refreshBtn');
    
    // Show loading
    loading.style.display = 'block';
    results.innerHTML = '';
    fetchBtn.disabled = true;
    refreshBtn.disabled = true;
    
    try {
        const response = await fetch('/api/posts', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                page_url: pageUrl,
                limit: postCount,
                force_refresh: forceRefresh
            })
        });
        
        const data = await response.json();
        
        // Hide loading
        loading.style.display = 'none';
        fetchBtn.disabled = false;
        refreshBtn.disabled = false;
        
        if (data.success) {
            currentPosts = data.posts;
            displayPosts(data);
        } else {
            results.innerHTML = `
                <div class="error">
                    <h3>❌ Error</h3>
                    <p>${data.error || 'Failed to fetch posts'}</p>
                </div>
            `;
        }
    } catch (error) {
        loading.style.display = 'none';
        fetchBtn.disabled = false;
        refreshBtn.disabled = false;
        results.innerHTML = `
            <div class="error">
                <h3>❌ Error</h3>
                <p>${error.message}</p>
            </div>
        `;
    }
}

function displayPosts(data) {
    const results = document.getElementById('results');
    const { posts, credits_used, credits_remaining, total_posts, cached } = data;
    
    let html = `
        <div class="stats">
            <span>📊 Posts: ${total_posts}</span>
            ${credits_used !== 0 ? `<span>💳 Credits used: ${credits_used}</span>` : ''}
            ${credits_remaining !== "N/A (cached)" ? `<span>💳 Remaining: ${credits_remaining}</span>` : ''}
            ${cached ? '<span style="color: #27ae60;">📦 Cached</span>' : ''}
        </div>
    `;
    
    posts.forEach((post, index) => {
        const reactionsHtml = Object.entries(post.reactions)
            .map(([key, value]) => `<span class="reaction">${key}: ${value}</span>`)
            .join('');
        
        const imagesHtml = post.images && post.images.length > 0
            ? post.images.map(img => `<img src="${img}" alt="Post image" onerror="this.style.display='none'" class="post-image">`).join('')
            : '';
        
        html += `
            <div class="post-card">
                <div class="post-header">
                    <span class="post-id">#${index + 1}</span>
                    <span class="post-time">🕐 ${post.time}</span>
                </div>
                <div class="post-text">${post.text}</div>
                ${imagesHtml ? `<div class="post-images">${imagesHtml}</div>` : ''}
                <div class="post-stats">
                    <span>❤️ ${post.total_reactions}</span>
                    <span>💬 ${post.comments}</span>
                    <span>🔄 ${post.shares}</span>
                </div>
                ${reactionsHtml ? `<div class="post-reactions">${reactionsHtml}</div>` : ''}
                ${post.post_link ? `<a href="${post.post_link}" target="_blank" class="post-link">🔗 View on Facebook</a>` : ''}
            </div>
        `;
    });
    
    results.innerHTML = html;
}

function setPage(url) {
    document.getElementById('pageUrl').value = url;
    // Auto-fetch when quick link is clicked
    fetchPosts(false);
}

// Auto-fetch on page load
document.addEventListener('DOMContentLoaded', () => {
    fetchPosts(false);
});
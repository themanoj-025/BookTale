"""Feed page route — social feed with compose box and tabs."""

from app.routes.social_shared import render_page


def render_feed_page() -> str:
    """Render the social feed page."""
    FEED_CONTENT = """<!-- Compose Box -->
<div class="compose-box animate-in">
  <form class="w-100" onsubmit="return submitPost()">
    <textarea id="postContent" class="w-100" placeholder="What\\'s happening?" aria-label="What\\'s happening?" rows="2" style="border:none;resize:none;font-size:1.1rem;padding:8px 0;background:transparent;color:var(--text);outline:none;font-family:var(--font);min-height:50px;"></textarea>
    <div class="compose-toolbar">
      <div>
        <button type="submit" class="btn btn-primary" id="postSubmitBtn"><i class="bi bi-feather"></i> Post</button>
      </div>
      <div class="text-muted small" id="postCharCount">0 / 500</div>
    </div>
  </form>
</div>

<!-- Feed Tabs -->
<nav class="d-flex border-bottom" style="border-color:var(--border);" aria-label="Feed tabs">
  <a href="#" class="feed-tab active" data-tab="following" onclick="switchFeedTab(this)">Following</a>
  <a href="#" class="feed-tab" data-tab="trending" onclick="switchFeedTab(this)">Trending</a>
  <a href="#" class="feed-tab" data-tab="discover" onclick="switchFeedTab(this)">Discover</a>
</nav>

<!-- Feed Content -->
<div id="feedContent" style="min-height:200px;">
  <div class="text-center py-5"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div></div>
</div>
"""
    return render_page(
        "Social Feed",
        FEED_CONTENT
        + """
<script>
var currentFeedTab = "following";
var currentFeedPage = 1;

function loadFeed(tab, page) {
  currentFeedTab = tab || currentFeedTab;
  currentFeedPage = page || 1;
  var c = document.getElementById("feedContent");
  if (!c) return;
  c.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div></div>';
  fetch("/api/feed?tab=" + currentFeedTab + "&page=" + currentFeedPage)
    .then(function(r){ return r.json() })
    .then(function(d) {
      if (!d.posts || !d.posts.length) {
        c.innerHTML = '<div class="empty-state empty-state-variant py-5"><div class="empty-icon"><i class="bi bi-inbox"></i></div><div class="empty-title">No posts yet</div><div class="empty-desc">Follow users or be the first to share what you are reading!</div><button class="empty-cta" onclick="document.getElementById(\\'postContent\\')?.focus()"><i class="bi bi-feather"></i> Create a Post</button></div>';
        return;
      }
      var html = "";
      d.posts.forEach(function(p) {
        var likedClass = p.is_liked ? " liked" : "";
        html += '<article class="post-card">';
        html += '<div class="post-card-body">';
        html += '<div class="post-card-header">' + p.author_avatar + ' <a href="/profile/' + p.user_id + '" class="post-author-name">' + p.author_name + '</a><span class="text-muted" style="font-size:.8rem;">' + (p.time_ago || "") + '</span></div>';
        html += '<div class="post-content-text">' + p.content + '</div>';
        html += '<div class="post-actions">';
        html += '<button class="post-action' + likedClass + '" onclick="likePost(\\'' + p.post_id + '\\',this)"><i class="bi bi-heart-fill"></i> ' + (p.likes_count || 0) + '</button>';
        html += '<button class="post-action" onclick="window.location.href=\\'/profile/' + p.user_id + '\\'"><i class="bi bi-chat-fill"></i> ' + (p.comment_count || 0) + '</button>';
        html += '</div></div></article>';
      });
      c.innerHTML = html;
    })
    .catch(function() {
      c.innerHTML = '<div class="empty-state empty-state-variant py-5"><div class="empty-icon"><i class="bi bi-wifi-off"></i></div><div class="empty-title">Could not load feed</div><div class="empty-desc">Check your connection and try again.</div><button class="empty-cta" onclick="loadFeed(\\'following\\',1)"><i class="bi bi-arrow-clockwise"></i> Retry</button></div>';
    });
}

function switchFeedTab(el) {
  document.querySelectorAll(".feed-tab").forEach(function(t){ t.classList.remove("active"); });
  el.classList.add("active");
  loadFeed(el.getAttribute("data-tab"), 1);
}

function submitPost() {
  var ta = document.getElementById("postContent");
  if (!ta) return false;
  var content = ta.value.trim();
  if (!content) { showToast("Write something!", "error"); return false; }
  fetch("/api/posts", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({content: content})
  }).then(function(r){ return r.json() }).then(function(d){
    if (d.success) {
      ta.value = "";
      showToast("Posted!", "success");
      loadFeed(currentFeedTab, 1);
    } else {
      showToast(d.error || "Failed to post", "error");
    }
  });
  return false;
}

function likePost(postId, btn) {
  fetch("/api/posts/" + postId + "/like", {method: "POST"})
    .then(function(r){ return r.json() })
    .then(function(d){
      if (btn) {
        var count = d.likes_count || 0;
        btn.innerHTML = (d.is_liked ? '<i class="bi bi-heart-fill"></i> ' : '<i class="bi bi-heart-fill"></i> ') + count;
        btn.classList.toggle("liked", d.is_liked);
      }
    });
}

document.addEventListener("DOMContentLoaded", function(){
  var ta = document.getElementById("postContent");
  var cc = document.getElementById("postCharCount");
  if (ta && cc) {
    ta.addEventListener("input", function(){
      var len = ta.value.length;
      cc.textContent = len + " / 500";
      if (len > 500) { ta.value = ta.value.substring(0,500); cc.textContent = "500 / 500"; }
    });
  }
  loadFeed("following", 1);
});
</script>
""",
    )

/**
 * notifications.js — Real-time Notifications Manager
 * Badge updates, mark read, real-time via SocketIO
 */

(function () {
  "use strict";

  let notifCount = 0;

  function updateBadge(count) {
    notifCount = count;
    // Update bell badge in top bar
    document
      .querySelectorAll(
        '.app-bar-icon [class*="bi-bell"] ~ .nav-badge, .nav-item-a [class*="bi-bell"] ~ .nav-badge',
      )
      .forEach(function (el) {
        el.textContent = count;
        el.style.display = count > 0 ? "" : "none";
      });
    // Update sidebar notification link
    document
      .querySelectorAll("#nav-notifications .nav-badge")
      .forEach(function (el) {
        if (el) {
          el.textContent = count;
          el.style.display = count > 0 ? "" : "none";
        }
      });
    // Update document title
    var title = document.title.replace(/^\(\d+\) /, "");
    if (count > 0) {
      document.title = "(" + count + ") " + title;
    }
  }

  function loadNotifications() {
    var container = document.getElementById("notifications-list");
    if (!container) return;

    // Show skeleton
    container.innerHTML =
      '<div class="skeleton" role="status" aria-label="Loading notifications" style="height:200px;margin:1rem;border-radius:12px;"></div>';

    fetch("/api/notifications")
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data || !Array.isArray(data) || data.length === 0) {
          container.innerHTML =
            '<div class="empty-state"><div class="empty-icon">🔔</div><div class="empty-title">No notifications yet</div><div class="empty-desc">When someone follows you, likes your post, or sends a challenge, you\'ll see it here.</div></div>';
          return;
        }

        var grouped = groupByDate(data);
        var html = '<ol class="notifications-list">';
        Object.keys(grouped).forEach(function (dateLabel) {
          html +=
            '<li class="day-separator"><time>' + dateLabel + "</time></li>";
          grouped[dateLabel].forEach(function (notif) {
            html +=
              '<article class="notification-item' +
              (notif.read ? "" : " unread") +
              '" aria-label="Notification">' +
              '<span class="notif-icon" aria-hidden="true">' +
              getNotifIcon(notif.type) +
              "</span>" +
              '<div class="notif-body">' +
              "<strong>" +
              (notif.actor_name || notif.actor_id || "Someone") +
              "</strong> " +
              notif.message +
              '<time datetime="' +
              notif.created_at +
              '">' +
              timeAgo(notif.created_at) +
              "</time>" +
              "</div>" +
              (notif.read
                ? ""
                : '<button class="btn btn-sm btn-outline" onclick="booktaleNotifs.markAsRead(\'' +
                  notif.id +
                  '\',this)" aria-label="Mark as read">✓</button>') +
              "</article>";
          });
        });
        html += "</ol>";
        container.innerHTML = html;
      })
      .catch(function (err) {
        console.error("Notifications load error:", err);
        container.innerHTML =
          '<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load notifications</div><button class="empty-cta" onclick="booktaleNotifs.loadNotifications()">Try Again</button></div>';
      });
  }

  function markAsRead(notifId, btn) {
    fetch("/api/notifications/" + notifId + "/read", { method: "POST" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data.success) {
          var article = btn.closest(".notification-item");
          if (article) {
            article.classList.remove("unread");
            if (btn) btn.remove();
          }
          // Recalculate unread count
          var unread = document.querySelectorAll(
            ".notification-item.unread",
          ).length;
          updateBadge(unread);
        }
      })
      .catch(function (err) {
        if (window.showToast) showToast("Error marking as read", "error");
      });
  }

  function markAllAsRead() {
    var btn = document.getElementById("markAllRead");
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    }

    fetch("/api/notifications/read-all", { method: "POST" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data.success) {
          document
            .querySelectorAll(".notification-item.unread")
            .forEach(function (el) {
              el.classList.remove("unread");
              var markBtn = el.querySelector("button");
              if (markBtn) markBtn.remove();
            });
          updateBadge(0);
          if (window.showToast)
            showToast("All notifications marked as read", "success");
        }
      })
      .catch(function (err) {
        if (window.showToast) showToast("Error", "error");
      })
      .finally(function () {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = "✓ Mark All Read";
        }
      });
  }

  // ─── Utility ────────────────────────────────────────────────

  function getNotifIcon(type) {
    var icons = {
      follow: "👤",
      like: "♥️",
      comment: "💬",
      repost: "↻",
      mention: "@",
      challenge: "🏆",
      achievement: "⭐",
      book_available: "📚",
      system: "🔔",
    };
    return icons[type] || "🔔";
  }

  function timeAgo(dateStr) {
    if (!dateStr) return "";
    var date = new Date(dateStr);
    var now = new Date();
    var diff = Math.floor((now - date) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    if (diff < 2592000) return Math.floor(diff / 86400) + "d ago";
    return date.toLocaleDateString();
  }

  function groupByDate(notifications) {
    var groups = {};
    var today = new Date().toDateString();
    var yesterday = new Date(Date.now() - 86400000).toDateString();

    notifications.forEach(function (n) {
      var d = new Date(n.created_at);
      var label;
      if (d.toDateString() === today) label = "Today";
      else if (d.toDateString() === yesterday) label = "Yesterday";
      else
        label = d.toLocaleDateString(undefined, {
          month: "long",
          day: "numeric",
        });

      if (!groups[label]) groups[label] = [];
      groups[label].push(n);
    });
    return groups;
  }

  // ─── Init ───────────────────────────────────────────────────

  function init() {
    // Load notifications if on notifications page
    if (document.getElementById("notifications-list")) {
      loadNotifications();
    }

    // Wire up mark-all-read button
    var markAllBtn = document.getElementById("markAllRead");
    if (markAllBtn) {
      markAllBtn.addEventListener("click", markAllAsRead);
    }

    // SocketIO integration for real-time updates.
    // Connect to the SAME namespace the server emits on (/social — see
    // realtime.py init_socketio). Previously this used bare io() (namespace
    // '/'), so the server's emit_notification(...) on /social never reached
    // the browser. The socket.io client script is served by flask-socketio at
    // /socket.io/socket.io.js and only loads when realtime is actually served.
    if (typeof io !== "undefined") {
      var socket = io("/social");
      // Exposed for the Playwright e2e suite (tests/e2e) so tests can wait for
      // the connection before asserting a cross-tab notification arrives.
      window.__booktaleSocket = socket;
      socket.on("notification", function (data) {
        if (data && data.count !== undefined) {
          updateBadge(data.count);
        }
        // Show toast for new notification
        if (data && data.message && window.showToast) {
          showToast(data.message, "info");
        }
        // Reload notifications if on notifications page
        if (document.getElementById("notifications-list")) {
          loadNotifications();
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.booktaleNotifs = {
    loadNotifications,
    markAsRead,
    markAllAsRead,
    updateBadge,
  };
})();

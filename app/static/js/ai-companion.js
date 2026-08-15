/**
 * ai-companion.js — AI Reading Companion
 * Floating chat widget with book recommendations, summaries, and discussion
 */

(function() {
  'use strict';

  var isOpen = false;

  function toggleCompanion() {
    var drawer = document.getElementById('aiCompanionDrawer');
    if (!drawer) return;
    isOpen = !isOpen;
    drawer.classList.toggle('open', isOpen);
    if (isOpen) {
      var input = document.getElementById('aiCompanionInput');
      if (input) setTimeout(function() { input.focus(); }, 300);
      if (drawer.querySelector('.ai-message.bot') === null) {
        addBotMessage('Hi! I\'m your AI Reading Companion. Ask me about book recommendations, summaries, or discussion questions!');
      }
    }
  }

  function sendMessage() {
    var input = document.getElementById('aiCompanionInput');
    if (!input) return;
    var text = input.value.trim();
    if (!text) return;

    addUserMessage(text);
    input.value = '';

    var messagesDiv = document.getElementById('aiCompanionMessages');
    if (messagesDiv) {
      messagesDiv.innerHTML += '<div class="ai-message bot" style="font-size:.8rem;color:var(--text-muted);"><div class="spinner-border spinner-border-sm me-2"></div>Thinking...</div>';
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    fetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      // Remove thinking indicator
      var thinking = document.querySelector('.ai-message.bot:last-child');
      if (thinking && thinking.textContent.includes('Thinking')) thinking.remove();
      
      if (data.error) {
        addBotMessage('Sorry, I couldn\'t process that. Please try again.');
        return;
      }
      addBotMessage(data.response || data.message || 'I\'m not sure how to answer that. Try asking about book recommendations!');
    })
    .catch(function() {
      var thinking = document.querySelector('.ai-message.bot:last-child');
      if (thinking && thinking.textContent.includes('Thinking')) thinking.remove();
      addBotMessage('Sorry, I\'m having trouble connecting. Please try again later.');
    });
  }

  function addUserMessage(text) {
    var container = document.getElementById('aiCompanionMessages');
    if (!container) return;
    container.innerHTML += '<div class="ai-message user">' + esc(text) + '</div>';
    container.scrollTop = container.scrollHeight;
  }

  function addBotMessage(text) {
    var container = document.getElementById('aiCompanionMessages');
    if (!container) return;
    container.innerHTML += '<div class="ai-message bot">' + esc(text) + '</div>';
    container.scrollTop = container.scrollHeight;
  }

  function esc(text) {
    if (!text) return '';
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(String(text)));
    return d.innerHTML;
  }

  // ─── Init ───────────────────────────────────────────────────

  function init() {
    // Wire up toggle button
    var toggleBtn = document.getElementById('aiCompanionToggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', toggleCompanion);
    }

    // Wire up send button
    var sendBtn = document.getElementById('aiCompanionSend');
    if (sendBtn) {
      sendBtn.addEventListener('click', sendMessage);
    }

    // Wire up input enter key
    var input = document.getElementById('aiCompanionInput');
    if (input) {
      input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendMessage();
        }
      });
    }

    // Wire up close button
    var closeBtn = document.getElementById('aiCompanionClose');
    if (closeBtn) {
      closeBtn.addEventListener('click', function() {
        var drawer = document.getElementById('aiCompanionDrawer');
        if (drawer) drawer.classList.remove('open');
        isOpen = false;
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.booktaleAI = { toggleCompanion, sendMessage };
})();

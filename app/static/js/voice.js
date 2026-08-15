/**
 * voice.js — Voice Diary Logging
 * Uses Web Speech API for dictation on diary entry form
 */

(function() {
  'use strict';

  var recognition = null;
  var isListening = false;

  function initVoiceDictation() {
    var btn = document.getElementById('voiceDictateBtn');
    if (!btn) return;

    // Check for browser support
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      btn.style.display = 'none';
      return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = function(event) {
      var textarea = document.getElementById('diaryContent');
      if (!textarea) return;
      var transcript = '';
      for (var i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      textarea.value = (textarea.value ? textarea.value + ' ' : '') + transcript;
    };

    recognition.onend = function() {
      isListening = false;
      if (btn) {
        btn.classList.remove('listening');
        btn.innerHTML = '🎤 Dictate';
        btn.setAttribute('aria-pressed', 'false');
      }
    };

    recognition.onerror = function(event) {
      isListening = false;
      if (btn) {
        btn.classList.remove('listening');
        btn.innerHTML = '🎤 Dictate';
        btn.setAttribute('aria-pressed', 'false');
      }
      if (window.showToast) {
        if (event.error === 'no-speech') showToast('No speech detected. Try again.', 'info');
        else if (event.error === 'not-allowed') showToast('Microphone access denied. Please allow microphone permissions.', 'error');
        else showToast('Voice recognition error: ' + event.error, 'error');
      }
    };

    btn.addEventListener('click', function() {
      if (isListening) {
        recognition.stop();
        isListening = false;
        btn.classList.remove('listening');
        btn.innerHTML = '🎤 Dictate';
        btn.setAttribute('aria-pressed', 'false');
        return;
      }

      try {
        recognition.start();
        isListening = true;
        btn.classList.add('listening');
        btn.innerHTML = '🔴 Stop';
        btn.setAttribute('aria-pressed', 'true');
        if (window.showToast) showToast('Listening... Speak now', 'info');
      } catch (e) {
        if (window.showToast) showToast('Could not start voice recognition', 'error');
      }
    });
  }

  function init() {
    if (document.getElementById('voiceDictateBtn')) {
      initVoiceDictation();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

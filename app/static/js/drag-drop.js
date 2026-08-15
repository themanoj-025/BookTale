/**
 * drag-drop.js — Drag & Drop for Favorites and Shelves
 * Enables drag-to-reorder for favorite books and shelf items
 */

(function() {
  'use strict';

  var dragSrcEl = null;

  function initDragDrop(containerSelector) {
    var containers = document.querySelectorAll(containerSelector || '[data-drag-container]');
    containers.forEach(function(container) {
      makeSortable(container);
    });
  }

  function makeSortable(container) {
    var items = container.querySelectorAll('[data-draggable]');
    items.forEach(function(item) {
      item.setAttribute('draggable', 'true');
      item.addEventListener('dragstart', handleDragStart);
      item.addEventListener('dragend', handleDragEnd);
      item.addEventListener('dragover', handleDragOver);
      item.addEventListener('dragenter', handleDragEnter);
      item.addEventListener('dragleave', handleDragLeave);
      item.addEventListener('drop', handleDrop);
    });
  }

  function handleDragStart(e) {
    dragSrcEl = this;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', this.innerHTML);
    this.classList.add('dragging');
  }

  function handleDragOver(e) {
    if (e.preventDefault) e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    return false;
  }

  function handleDragEnter(e) {
    this.classList.add('drag-over');
  }

  function handleDragLeave(e) {
    this.classList.remove('drag-over');
  }

  function handleDrop(e) {
    if (e.stopPropagation) e.stopPropagation();
    if (dragSrcEl !== this) {
      // Swap the items
      var parent = this.parentNode;
      var items = Array.from(parent.querySelectorAll('[data-draggable]'));
      var srcIdx = items.indexOf(dragSrcEl);
      var tgtIdx = items.indexOf(this);
      
      if (srcIdx < tgtIdx) {
        parent.insertBefore(dragSrcEl, this.nextSibling);
      } else {
        parent.insertBefore(dragSrcEl, this);
      }
    }
    this.classList.remove('drag-over');
    return false;
  }

  function handleDragEnd(e) {
    this.classList.remove('dragging');
    document.querySelectorAll('[data-draggable]').forEach(function(el) {
      el.classList.remove('drag-over');
    });

    // Save new order
    var container = this.closest('[data-drag-container]');
    if (container) {
      var orderedIds = Array.from(container.querySelectorAll('[data-draggable]'))
        .map(function(el) { return el.getAttribute('data-id'); })
        .filter(function(id) { return id; });
      
      if (orderedIds.length > 0) {
        var endpoint = container.getAttribute('data-save-endpoint');
        if (endpoint) {
          fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order: orderedIds })
          }).catch(function() {});
        }
      }
    }
  }

  // ─── Init ───────────────────────────────────────────────────

  function init() {
    if (document.querySelector('[data-drag-container]')) {
      initDragDrop();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.booktaleDragDrop = { initDragDrop };
})();

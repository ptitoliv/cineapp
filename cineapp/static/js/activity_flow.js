/* ==========================================================================
   activity_flow.js — shared renderer for the activity feed

   Consumed by both the dashboard activity card (show_dashboard.html) and
   the full activity feed page (show_activity_flow.html). Both pages hit the
   same endpoint (main.update_activity_flow), receive the same structured
   per-entry payload, and reuse this renderer to build identical timeline
   nodes. Styles live in styles.css [ACTIVITY_FLOW].

   The DataTables init itself is kept page-local (paging settings, layout,
   length menu wiring) — only the rendering is shared.
   ========================================================================== */

// escapeHtml lives in static/js/utils.js (loaded from base.html).

// Type pill — taxonomy shared with the dashboard and the full feed.
function activity_kind(row) {
  switch (row.action_type) {
    case "shows":     return { cls: "entree",      label: "Entrée" };
    case "marks":     return row.mark.is_homework_mark
                              ? { cls: "devoir", label: "Devoir" }
                              : { cls: "note",   label: "Note" };
    case "homeworks": return { cls: "devoir",      label: "Devoir" };
    case "comments":  return { cls: "commentaire", label: "Commentaire" };
    case "favorites": return { cls: "favori",      label: "Favori" };
    default:          return { cls: "note",        label: row.action_type };
  }
}

// Natural-language sentence rendered inside the timeline node.
function activity_phrase(row) {
  var who  = '<strong>' + escapeHtml(row.user.nickname) + '</strong>';
  var what = '<a href="' + escapeHtml(row.show.url) + '">' + escapeHtml(row.show.name) + '</a>';
  switch (row.action_type) {
    case "shows":
      return who + ' a ajouté ' + what + '.';
    case "marks":
      var note = '<span class="mark">' + row.mark.value + '</span>';
      if (row.mark.is_homework_mark) {
        return who + ' a rempli son devoir sur ' + what + ' avec la note ' + note;
      }
      return who + ' a noté ' + what + ' ' + note;
    case "homeworks":
      return who + ' a donné ' + what + ' en devoir à <strong>'
           + escapeHtml(row.target_user.nickname) + '</strong>.';
    case "comments":
      return who + ' a commenté la note de <strong>'
           + escapeHtml(row.parent_mark.user.nickname) + '</strong> sur ' + what + '.';
    case "favorites":
      return who + ' a ajouté ' + what + ' à ses favoris <span class="star">★</span>';
  }
  return "";
}

// Optional quote body : the review HTML (marks — server-side sanitized on
// write via sanitize_comment(), so injected raw like the list-page bubble) or
// the sub-comment text (comments — plain text, escaped).
function activity_quote(row) {
  if (row.action_type === "comments" && row.comment && row.comment.message) {
    return '<div class="act-quote">' + escapeHtml(row.comment.message) + '</div>';
  }
  if (row.action_type === "marks" && row.mark && row.mark.comment) {
    return '<div class="act-quote">' + row.mark.comment + '</div>';
  }
  return "";
}

function activity_render_node(row) {
  var kind    = activity_kind(row);
  var color   = row.user.theme_color || "#1c1820";
  var initial = (row.user.nickname || "?").charAt(0).toUpperCase();
  var avatar  = '<span class="act-av" style="background:' + escapeHtml(color) + ';">'
              + escapeHtml(initial) + '</span>';
  var when    = row.when ? '<span class="act-when">' + escapeHtml(row.when) + '</span>' : '';

  return '<article class="act-node">'
       +   '<span class="act-marker k-' + kind.cls + '">' + kind.label + '</span>'
       +   '<div class="act-body">'
       +     '<div class="act-head">'
       +       '<p class="act-phrase">' + avatar + activity_phrase(row) + '</p>'
       +       when
       +     '</div>'
       +     activity_quote(row)
       +   '</div>'
       + '</article>';
}

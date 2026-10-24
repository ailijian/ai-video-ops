// Presentation only: native details state and in-page navigation never submit a review.
export function enhanceReviewDisclosures(root) {
  for (const summary of root.querySelectorAll('details > summary')) {
    if (summary.querySelector('[data-disclosure-affordance]')) continue;
    const hint = summary.ownerDocument.createElement('span');
    hint.dataset.disclosureAffordance = '';
    hint.className = 'customer-disclosure-affordance';
    hint.innerHTML = '<span class="disclosure-closed">展开</span><span class="disclosure-open">收起</span><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m6 9 6 6 6-6"/></svg>';
    summary.classList.add('customer-disclosure-summary');
    summary.append(hint);
  }
}

export function bindReviewReturnLinks(root, scope = root) {
  for (const button of root.querySelectorAll('[data-review-section-target]')) {
    button.addEventListener('click', () => {
      const section = scope.querySelector(`#${button.dataset.reviewSectionTarget}`);
      if (!section) return;
      // Previously saved facts remain available in their original location.
      const known = section.querySelector?.('details.known-facts-disclosure');
      if (known) known.open = true;
      section.tabIndex = -1;
      section.focus({preventScroll: true});
      section.scrollIntoView({block: 'start'});
    });
  }
}

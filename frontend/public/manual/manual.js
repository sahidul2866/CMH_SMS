document.getElementById('print').addEventListener('click', () => window.print());
// Include the expandable reference notes when printing, then restore their state.
let previouslyOpen = [];
window.addEventListener('beforeprint', () => {
  previouslyOpen = [...document.querySelectorAll('details')].filter(item => item.open);
  document.querySelectorAll('details').forEach(item => { item.open = true; });
});
window.addEventListener('afterprint', () => {
  document.querySelectorAll('details').forEach(item => { item.open = previouslyOpen.includes(item); });
});

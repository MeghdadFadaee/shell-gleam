'use strict';
const BASE_URL = 'https://meghdadfadaee.github.io/shell-gleam';
const form = document.querySelector('#config-form');
const dashboard = document.querySelector('#dashboard');
const commandNode = document.querySelector('#install-command');
const statusNode = document.querySelector('#copy-status');
let health = 'healthy';
let wizard = false;

function quoteShell(value) {
  return "'" + value.replace(/'/g, "'\\''") + "'";
}
function commandFor({ title, ascii, color, wizard }) {
  let command = `curl -fsSL ${BASE_URL}/setup.sh | bash`;
  const args = [];
  if (title && title !== 'ORBIT') args.push('--title', quoteShell(title));
  if (ascii) args.push('--ascii');
  if (!color) args.push('--no-color');
  if (wizard) args.push('--wizard');
  if (args.length) command += ' -s -- install ' + args.join(' ');
  return command;
}
function render() {
  const title = (form.elements.title.value.trim() || 'ORBIT').replace(/[\u0000-\u001f\u007f]/g, '');
  const ascii = form.elements.ascii.checked;
  const color = form.elements.color.checked;
  const warning = health === 'attention';
  const width = 66;
  const horizontal = ascii ? '-' : '─';
  const vertical = ascii ? '|' : '│';
  const symbol = { diamond: ascii ? '*' : '◆', dot: ascii ? '*' : '●', tick: ascii ? '+' : '✓', warn: ascii ? '!' : '⚠', up: ascii ? '^' : '↑' };
  function add(text, className = '') {
    const node = document.createElement('span');
    if (color) node.className = className;
    node.textContent = text + '\n';
    dashboard.append(node);
  }
  function line(text = '', className = '') {
    const content = Array.from(text).slice(0, width - 2).join('');
    add(vertical + ' ' + content.padEnd(width - 2) + ' ' + vertical, className);
  }
  function divider(label) {
    const content = horizontal + ' ' + label + ' ';
    add((ascii ? '+' : '├') + content + horizontal.repeat(width - content.length) + (ascii ? '+' : '┤'), 'term-border');
  }
  const bar = (filled) => (ascii ? '#' : '█').repeat(filled) + (ascii ? '-' : '░').repeat(18 - filled);
  dashboard.replaceChildren();
  add((ascii ? '+' : '╭') + horizontal.repeat(width) + (ascii ? '+' : '╮'), 'term-border');
  const right = symbol.dot + ' ' + (warning ? 'ATTENTION' : 'HEALTHY');
  const left = symbol.diamond + ' ' + Array.from(title.toUpperCase()).slice(0, 32).join('');
  line(left + ' '.repeat(Math.max(2, width - 2 - Array.from(left).length - right.length)) + right, warning ? 'term-warning' : 'term-good');
  line('  Ubuntu 24.04 LTS  /  192.0.2.10', 'term-dim');
  divider('SYSTEM'); line();
  line(`  ${symbol.up} Uptime  12d 4h    ${ascii ? '~' : '≋'} Load average  0.24 (8 cores)`, 'term-title');
  line(`  Memory  ${bar(4)}  23% / 3.7 / 16.0 GiB`, 'term-good');
  line(`  Disk /  ${bar(warning ? 16 : 6)}  ${warning ? '91%' : '34%'} / ${warning ? '182' : '68'} / 200 GiB`, warning ? 'term-warning' : 'term-good'); line();
  divider('RUNTIME'); line();
  line(`  ${symbol.dot}  Nginx is online`, 'term-good');
  line(`  ${symbol.dot}  Docker is online`, 'term-good');
  line(warning ? '     4 running / 1 unhealthy / 0 failed' : '     4 containers running / 4 healthchecked', warning ? 'term-warning' : 'term-good'); line();
  divider('HEALTH'); line();
  line(warning ? `  ${symbol.warn}  1 unit failed / worker.service` : `  ${symbol.tick}  No failed systemd units`, warning ? 'term-warning' : 'term-good');
  line(`  ${symbol.tick}  Packages current (cached)`, 'term-good');
  line(`  ${symbol.tick}  No reboot needed`, 'term-good'); line();
  add((ascii ? '+' : '╰') + horizontal.repeat(width) + (ascii ? '+' : '╯'), 'term-border');
  commandNode.textContent = commandFor({ title, ascii, color, wizard });
  statusNode.textContent = '';
}
form.addEventListener('input', render);
form.addEventListener('submit', (event) => event.preventDefault());
document.querySelectorAll('[data-state]').forEach(button => {
  button.addEventListener('click', () => {
    health = button.dataset.state;
    document.querySelectorAll('[data-state]').forEach(item => {
      const selected = item === button;
      item.classList.toggle('selected', selected);
      item.setAttribute('aria-pressed', String(selected));
    });
    render();
  });
});
document.querySelector('#wizard-toggle').addEventListener('click', event => {
  wizard = !wizard;
  event.currentTarget.setAttribute('aria-pressed', String(wizard));
  event.currentTarget.textContent = wizard ? 'Setup wizard included ✓' : 'Use the setup wizard →';
  render();
});
document.querySelector('#copy-command').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(commandNode.textContent);
    statusNode.textContent = 'Copied. Your next login is looking brighter.';
  } catch {
    const range = document.createRange();
    range.selectNodeContents(commandNode);
    const selection = window.getSelection();
    selection.removeAllRanges(); selection.addRange(range);
    statusNode.textContent = 'Command selected. Press Ctrl+C (or Cmd+C) to copy.';
  }
});
render();

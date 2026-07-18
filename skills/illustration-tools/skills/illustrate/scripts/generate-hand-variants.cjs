#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const rough = require('roughjs');
const { JSDOM } = require('jsdom');
const { SVGPathData } = require('svg-pathdata');

const ROOT = path.resolve(__dirname, '..');
const ASSETS = path.join(ROOT, 'assets');
const TYPES = [
  'architecture',
  'flowchart',
  'sequence',
  'state',
  'er',
  'timeline',
  'swimlane',
  'quadrant',
  'nested',
  'tree',
  'org-chart',
  'layers',
  'venn',
  'pyramid',
  'bar',
  'data-flow',
  'dp-integration',
  'dp-security-matrix',
  'gantt',
  'high-level',
  'it-state',
  'line',
  'loop',
  'medallion',
  'process',
  'radar',
  'scatter',
  'datalake',
  'high-level-vertical'
];

const PAPER = '#f5f5f5';
const ROUGHNESS = 1.45;
const BOWING = 1.25;
const FILL_INSET = 2;

function attr(el, name, fallback = null) {
  return el.hasAttribute(name) ? el.getAttribute(name) : fallback;
}

function numberAttr(el, name, fallback = 0) {
  const value = attr(el, name);
  if (value === null || value === '') return fallback;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function makeSvgEl(doc, tagName) {
  return doc.createElementNS('http://www.w3.org/2000/svg', tagName);
}

function copyAttrs(from, to, names) {
  for (const name of names) {
    if (from.hasAttribute(name)) to.setAttribute(name, from.getAttribute(name));
  }
}

function shouldCopyPlain(el) {
  const tag = el.tagName.toLowerCase();
  if (tag !== 'rect') return false;

  const width = attr(el, 'width');
  const height = attr(el, 'height');
  const stroke = attr(el, 'stroke');
  const fill = attr(el, 'fill');

  if (width === '100%' && height === '100%') {
    return true;
  }

  const numericHeight = numberAttr(el, 'height', -1);
  return stroke === null && numericHeight === 12 && fill === PAPER;
}

function roughOptions(el, seed) {
  const tag = el.tagName.toLowerCase();
  const stroke = attr(el, 'stroke', tag === 'line' || tag === 'path' ? '#2d3142' : 'none');
  const strokeWidth = numberAttr(el, 'stroke-width', 1);

  return {
    seed,
    roughness: ROUGHNESS,
    bowing: BOWING,
    stroke,
    strokeWidth,
    fill: 'none',
    fillStyle: 'solid',
    disableMultiStroke: true,
    disableMultiStrokeFill: true,
    preserveVertices: true
  };
}

function isVisiblePaint(value) {
  return value !== null && value !== '' && value !== 'none' && value !== 'transparent';
}

function hasVisibleFill(el) {
  return isVisiblePaint(attr(el, 'fill'));
}

function hasVisibleStroke(el) {
  return isVisiblePaint(attr(el, 'stroke'));
}

function fmt(value) {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(3)));
}

function seededRandom(seed) {
  let state = Math.abs(seed) % 2147483647;
  if (state === 0) state = 1;
  return () => {
    state = state * 16807 % 2147483647;
    return (state - 1) / 2147483646;
  };
}

function jitter(rand, amount) {
  return (rand() * 2 - 1) * amount;
}

function jitteredRectFillPath(x, y, w, h, seed) {
  const rand = seededRandom(seed);
  const amp = Math.min(1.4, Math.max(0.35, Math.min(w, h) * 0.08));
  const stepsX = Math.max(2, Math.ceil(w / 44));
  const stepsY = Math.max(2, Math.ceil(h / 44));
  const points = [];

  for (let i = 0; i <= stepsX; i++) {
    const t = i / stepsX;
    points.push([x + w * t, y + jitter(rand, amp)]);
  }
  for (let i = 1; i <= stepsY; i++) {
    const t = i / stepsY;
    points.push([x + w + jitter(rand, amp), y + h * t]);
  }
  for (let i = 1; i <= stepsX; i++) {
    const t = i / stepsX;
    points.push([x + w * (1 - t), y + h + jitter(rand, amp)]);
  }
  for (let i = 1; i < stepsY; i++) {
    const t = i / stepsY;
    points.push([x + jitter(rand, amp), y + h * (1 - t)]);
  }

  return `M${points.map(([px, py]) => `${fmt(px)} ${fmt(py)}`).join(' L')} Z`;
}

function jitteredEllipseFillPath(cx, cy, rx, ry, seed) {
  const rand = seededRandom(seed);
  const amp = Math.min(1.4, Math.max(0.35, Math.min(rx, ry) * 0.08));
  const points = [];
  const steps = 28;

  for (let i = 0; i < steps; i++) {
    const angle = (Math.PI * 2 * i) / steps;
    points.push([
      cx + Math.cos(angle) * (rx + jitter(rand, amp)),
      cy + Math.sin(angle) * (ry + jitter(rand, amp))
    ]);
  }

  return `M${points.map(([px, py]) => `${fmt(px)} ${fmt(py)}`).join(' L')} Z`;
}

function insetPoints(points) {
  if (points.length < 3) return points;

  const center = points.reduce(
    (acc, [x, y]) => ({ x: acc.x + x / points.length, y: acc.y + y / points.length }),
    { x: 0, y: 0 }
  );
  const radius = Math.max(
    ...points.map(([x, y]) => Math.hypot(x - center.x, y - center.y)),
    FILL_INSET
  );
  const scale = Math.max(0.8, 1 - FILL_INSET / radius);

  return points.map(([x, y]) => [
    center.x + (x - center.x) * scale,
    center.y + (y - center.y) * scale
  ]);
}

function appendPlainFill(doc, group, el, seed) {
  if (!hasVisibleFill(el)) return;

  const tag = el.tagName.toLowerCase();
  let fillEl = makeSvgEl(doc, 'path');
  let d = null;

  if (tag === 'rect') {
    const x = numberAttr(el, 'x');
    const y = numberAttr(el, 'y');
    const w = numberAttr(el, 'width');
    const h = numberAttr(el, 'height');
    if (w <= FILL_INSET * 2 || h <= FILL_INSET * 2) return;

    d = jitteredRectFillPath(x + FILL_INSET, y + FILL_INSET, w - FILL_INSET * 2, h - FILL_INSET * 2, seed + 131);
  } else if (tag === 'circle') {
    const r = numberAttr(el, 'r');
    if (r <= FILL_INSET) return;

    d = jitteredEllipseFillPath(numberAttr(el, 'cx'), numberAttr(el, 'cy'), r - FILL_INSET, r - FILL_INSET, seed + 131);
  } else if (tag === 'ellipse') {
    const rx = numberAttr(el, 'rx');
    const ry = numberAttr(el, 'ry');
    if (rx <= FILL_INSET || ry <= FILL_INSET) return;

    d = jitteredEllipseFillPath(numberAttr(el, 'cx'), numberAttr(el, 'cy'), rx - FILL_INSET, ry - FILL_INSET, seed + 131);
  } else if (tag === 'polygon') {
    const points = insetPoints(parsePoints(attr(el, 'points')));
    if (!points.length) return;

    d = `M${points.map(([x, y]) => `${fmt(x)} ${fmt(y)}`).join(' L')} Z`;
  } else if (tag === 'path') {
    d = attr(el, 'd', '');
  }

  if (!d) return;

  fillEl.setAttribute('class', 'rough-fill-mask');
  fillEl.setAttribute('d', d);
  fillEl.setAttribute('fill', attr(el, 'fill'));
  fillEl.setAttribute('stroke', 'none');
  copyAttrs(el, fillEl, ['fill-opacity', 'fill-rule']);
  group.appendChild(fillEl);
}

function appendRoughDrawable(doc, group, generator, drawable, sourceEl) {
  const dash = attr(sourceEl, 'stroke-dasharray');
  const paths = generator.toPaths(drawable);

  for (const roughPath of paths) {
    const pathEl = makeSvgEl(doc, 'path');
    pathEl.setAttribute('class', 'rough-generated');
    pathEl.setAttribute('d', roughPath.d);
    pathEl.setAttribute('stroke', roughPath.stroke || 'none');
    pathEl.setAttribute('stroke-width', String(roughPath.strokeWidth ?? 0));
    pathEl.setAttribute('fill', roughPath.fill || 'none');
    pathEl.setAttribute('stroke-linecap', 'round');
    pathEl.setAttribute('stroke-linejoin', 'round');
    if (dash && roughPath.fill === 'none') pathEl.setAttribute('stroke-dasharray', dash);
    group.appendChild(pathEl);
  }
}

function roundedRectPath(x, y, w, h, rx, ry) {
  const rX = Math.max(0, Math.min(rx, w / 2));
  const rY = Math.max(0, Math.min(ry, h / 2));
  if (!rX && !rY) return `M${x} ${y} H${x + w} V${y + h} H${x} Z`;
  return [
    `M${x + rX} ${y}`,
    `H${x + w - rX}`,
    `Q${x + w} ${y} ${x + w} ${y + rY}`,
    `V${y + h - rY}`,
    `Q${x + w} ${y + h} ${x + w - rX} ${y + h}`,
    `H${x + rX}`,
    `Q${x} ${y + h} ${x} ${y + h - rY}`,
    `V${y + rY}`,
    `Q${x} ${y} ${x + rX} ${y}`,
    'Z'
  ].join(' ');
}

function parsePoints(value) {
  return String(value || '')
    .trim()
    .split(/\s+/)
    .map(pair => pair.split(',').map(Number))
    .filter(pair => pair.length === 2 && pair.every(Number.isFinite));
}

function pathEndpoint(d) {
  try {
    const commands = new SVGPathData(d).toAbs().commands;
    let current = null;
    let previous = null;
    let start = null;

    for (const command of commands) {
      switch (command.type) {
        case SVGPathData.MOVE_TO:
          previous = current;
          current = { x: command.x, y: command.y };
          start = { ...current };
          break;
        case SVGPathData.HORIZ_LINE_TO:
          previous = current;
          current = { x: command.x, y: current ? current.y : 0 };
          break;
        case SVGPathData.VERT_LINE_TO:
          previous = current;
          current = { x: current ? current.x : 0, y: command.y };
          break;
        case SVGPathData.LINE_TO:
          previous = current;
          current = { x: command.x, y: command.y };
          break;
        case SVGPathData.CURVE_TO:
          previous = { x: command.x2, y: command.y2 };
          current = { x: command.x, y: command.y };
          break;
        case SVGPathData.SMOOTH_CURVE_TO:
          previous = { x: command.x2, y: command.y2 };
          current = { x: command.x, y: command.y };
          break;
        case SVGPathData.QUAD_TO:
          previous = { x: command.x1, y: command.y1 };
          current = { x: command.x, y: command.y };
          break;
        case SVGPathData.SMOOTH_QUAD_TO:
          previous = current;
          current = { x: command.x, y: command.y };
          break;
        case SVGPathData.CLOSE_PATH:
          previous = current;
          current = start ? { ...start } : current;
          break;
        default:
          if ('x' in command && 'y' in command) {
            previous = current;
            current = { x: command.x, y: command.y };
          }
      }
    }

    if (current && previous) return { tip: current, previous };
  } catch (_) {
    return null;
  }
  return null;
}

function markerEndpoint(el) {
  const tag = el.tagName.toLowerCase();
  if (tag === 'line') {
    return {
      tip: { x: numberAttr(el, 'x2'), y: numberAttr(el, 'y2') },
      previous: { x: numberAttr(el, 'x1'), y: numberAttr(el, 'y1') }
    };
  }
  if (tag === 'path') return pathEndpoint(attr(el, 'd', ''));
  if (tag === 'polyline' || tag === 'polygon') {
    const points = parsePoints(attr(el, 'points'));
    if (points.length >= 2) {
      const [px, py] = points[points.length - 2];
      const [tx, ty] = points[points.length - 1];
      return { tip: { x: tx, y: ty }, previous: { x: px, y: py } };
    }
  }
  return null;
}

function appendArrowhead(doc, group, generator, sourceEl, seed) {
  if (!sourceEl.hasAttribute('marker-end')) return;

  const endpoint = markerEndpoint(sourceEl);
  if (!endpoint) return;

  const { tip, previous } = endpoint;
  const dx = tip.x - previous.x;
  const dy = tip.y - previous.y;
  const length = Math.hypot(dx, dy);
  if (!length) return;

  const ux = dx / length;
  const uy = dy / length;
  const px = -uy;
  const py = ux;
  const stroke = attr(sourceEl, 'stroke', '#4f5d75');
  const strokeWidth = numberAttr(sourceEl, 'stroke-width', 1);
  const headLength = 8 + strokeWidth * 2;
  const headWidth = 6 + strokeWidth * 2;
  const base = {
    x: tip.x - ux * headLength,
    y: tip.y - uy * headLength
  };

  const points = [
    [tip.x, tip.y],
    [base.x + px * headWidth / 2, base.y + py * headWidth / 2],
    [base.x - px * headWidth / 2, base.y - py * headWidth / 2]
  ];

  const drawable = generator.polygon(points, {
    seed: seed + 997,
    roughness: ROUGHNESS,
    bowing: BOWING,
    stroke,
    strokeWidth,
    fill: stroke,
    fillStyle: 'solid',
    disableMultiStroke: true,
    disableMultiStrokeFill: true,
    preserveVertices: true
  });
  appendRoughDrawable(doc, group, generator, drawable, sourceEl);
}

function convertGeometry(doc, el, generator, seed) {
  const tag = el.tagName.toLowerCase();
  const options = roughOptions(el, seed);

  const group = makeSvgEl(doc, 'g');
  group.setAttribute('class', 'rough-shape');
  group.setAttribute('data-source-tag', tag);
  if (el.hasAttribute('marker-end')) group.setAttribute('data-rough-arrowhead', 'true');
  copyAttrs(el, group, ['clip-path', 'mask', 'transform', 'opacity']);
  appendPlainFill(doc, group, el, seed);

  if (!hasVisibleStroke(el)) {
    appendArrowhead(doc, group, generator, el, seed);
    return group;
  }

  let drawable = null;
  if (tag === 'rect') {
    const x = numberAttr(el, 'x');
    const y = numberAttr(el, 'y');
    const w = numberAttr(el, 'width');
    const h = numberAttr(el, 'height');
    const rx = numberAttr(el, 'rx');
    const ry = numberAttr(el, 'ry', rx);
    drawable = rx || ry
      ? generator.path(roundedRectPath(x, y, w, h, rx, ry), options)
      : generator.rectangle(x, y, w, h, options);
  } else if (tag === 'line') {
    drawable = generator.line(
      numberAttr(el, 'x1'),
      numberAttr(el, 'y1'),
      numberAttr(el, 'x2'),
      numberAttr(el, 'y2'),
      options
    );
  } else if (tag === 'path') {
    drawable = generator.path(attr(el, 'd', ''), options);
  } else if (tag === 'polygon') {
    drawable = generator.polygon(parsePoints(attr(el, 'points')), options);
  } else if (tag === 'polyline') {
    drawable = generator.linearPath(parsePoints(attr(el, 'points')), options);
  } else if (tag === 'circle') {
    const r = numberAttr(el, 'r');
    drawable = generator.circle(numberAttr(el, 'cx'), numberAttr(el, 'cy'), r * 2, options);
  } else if (tag === 'ellipse') {
    drawable = generator.ellipse(numberAttr(el, 'cx'), numberAttr(el, 'cy'), numberAttr(el, 'rx') * 2, numberAttr(el, 'ry') * 2, options);
  }

  if (!drawable) return el.cloneNode(true);
  appendRoughDrawable(doc, group, generator, drawable, el);
  appendArrowhead(doc, group, generator, el, seed);
  return group;
}

function convertNode(doc, node, generator, seedRef) {
  if (node.nodeType === 8) return doc.createComment(node.nodeValue);
  if (node.nodeType !== 1) return node.cloneNode(true);

  const el = node;
  const tag = el.tagName.toLowerCase();

  if (tag === 'defs') {
    const clone = el.cloneNode(false);
    for (const child of Array.from(el.childNodes)) {
      if (child.nodeType === 1 && child.tagName.toLowerCase() === 'marker') continue;
      clone.appendChild(child.cloneNode(true));
    }
    return clone;
  }

  if (tag === 'text' || tag === 'title' || tag === 'desc') {
    return el.cloneNode(true);
  }

  if (tag === 'g' || tag === 'a' || tag === 'svg') {
    const clone = el.cloneNode(false);
    for (const child of Array.from(el.childNodes)) {
      clone.appendChild(convertNode(doc, child, generator, seedRef));
    }
    return clone;
  }

  if (['rect', 'line', 'path', 'polygon', 'polyline', 'circle', 'ellipse'].includes(tag)) {
    if (shouldCopyPlain(el)) return el.cloneNode(true);
    seedRef.value += 17;
    return convertGeometry(doc, el, generator, seedRef.value);
  }

  return el.cloneNode(true);
}

function addHandMetadata(document) {
  const title = document.querySelector('head > title');
  if (title && !title.textContent.includes('Hand-drawn')) {
    title.textContent = `${title.textContent} · Hand-drawn`;
  }
  const eyebrow = document.querySelector('.eyebrow');
  if (eyebrow && !eyebrow.textContent.includes('Hand')) {
    eyebrow.textContent = `${eyebrow.textContent} · Hand`;
  }
}

function stripOldHandFilter(document) {
  for (const style of Array.from(document.querySelectorAll('style'))) {
    style.textContent = style.textContent
      .replace(/\/\* Hand variant:[\s\S]*?svg \.label-mask \{\s*filter: none;\s*\}\s*/g, '')
      .replace(/svg:has\(#sketchy\)[\s\S]*?\}\s*/g, '');
  }
}

function convertFile(sourceName, targetName, seedBase) {
  const sourcePath = path.join(ASSETS, sourceName);
  const targetPath = path.join(ASSETS, targetName);
  const dom = new JSDOM(fs.readFileSync(sourcePath, 'utf8'), { contentType: 'text/html' });
  const { document } = dom.window;
  const svg = document.querySelector('svg');
  if (!svg) throw new Error(`No <svg> found in ${sourceName}`);

  addHandMetadata(document);
  stripOldHandFilter(document);

  const generator = rough.generator({ options: { seed: seedBase } });
  const convertedSvg = svg.cloneNode(false);
  const seedRef = { value: seedBase };
  for (const child of Array.from(svg.childNodes)) {
    convertedSvg.appendChild(convertNode(document, child, generator, seedRef));
  }
  svg.replaceWith(convertedSvg);

  fs.writeFileSync(targetPath, dom.serialize(), 'utf8');
}

let index = 1;
for (const type of TYPES) {
  convertFile(`example-${type}.html`, `example-${type}-hand.html`, 1000 + index * 101);
  index += 1;
}
convertFile('template.html', 'template-hand.html', 5000);

console.log(`Generated ${TYPES.length} hand examples plus template-hand.html`);

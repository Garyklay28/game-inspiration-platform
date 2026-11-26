// Figma 에 board*.svg 를 넣은 뒤 use_figma 로 한 번 실행하는 정리 스크립트 (Plugin API).
// PAIRS 의 보드 ID(업로드 응답의 placedOnNodeId)와 섹션 ID 를 바꿔서 쓴다.
// 하는 일: ① 보드를 장별 섹션에 넣고 가로로 배치 ② ∗(U+2217) → * 복원
//          ③ 레이어 이름 c<폭>_n / e<폭>_n 으로 남긴 원래 폭을 이용해, 글꼴이 Inter 로 바뀐 뒤에도 가운데 정렬 유지
//          ④ &lt; 등 문자 엔티티 복원, 제목 백틱 제거, 텍스트 레이어 이름을 내용으로
const PAGE_ID = '113:2';
const PAIRS = [ /* ['보드ID', '섹션ID'], ... 0~7 장 순서 */ ];
const page = await figma.getNodeByIdAsync(PAGE_ID);
await figma.setCurrentPageAsync(page);
const PAD = 80, GAP = 240;
const ent = s => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
let x = 0; const out = [];
for (const [bid, sid] of PAIRS) {
  const b = await figma.getNodeByIdAsync(bid), sec = await figma.getNodeByIdAsync(sid);
  if (b.parent.id !== sec.id) sec.appendChild(b);
  for (const t of b.findAllWithCriteria({ types: ['TEXT'] })) {
    const fixedText = ent(t.characters.replace(/∗/g, '*').replace(/`/g, ''));
    if (fixedText !== t.characters) {
      for (const f of t.getRangeAllFontNames(0, t.characters.length)) await figma.loadFontAsync(f);
      t.characters = fixedText;
    }
    const m = /^([cse])(-?[\d.]+)_\d+$/.exec(t.name);
    if (m && m[1] !== 's') { const w0 = parseFloat(m[2]); t.x += m[1] === 'c' ? (w0 - t.width) / 2 : (w0 - t.width); }
    t.name = t.characters.slice(0, 60) || 'text';
  }
  sec.resizeWithoutConstraints(b.width + PAD * 2, b.height + PAD * 2);
  sec.x = x; sec.y = 0; b.x = PAD; b.y = PAD; x += sec.width + GAP;
  out.push({ section: sec.name, board: b.id });
}
return out;

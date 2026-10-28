import { DailySlip } from '../../core/daily';

const W = 1080;
const H = 1350; // 4:5, il formato verticale di Instagram
const AMBER = '#ffc61a';
const TEXT = '#e9f2ec';
const MUTED = '#8fa89a';

/** Spezza un testo su più righe dentro la larghezza data */
function lines(ctx: CanvasRenderingContext2D, text: string, width: number): string[] {
  const out: string[] = [];
  let line = '';
  for (const word of text.split(' ')) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > width && line) {
      out.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) out.push(line);
  return out;
}

/** Immagine della schedina da condividere: niente nomi di bookmaker né link, solo i pronostici e i numeri di Archie */
export async function slipImage(s: DailySlip): Promise<Blob> {
  await document.fonts?.ready;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d')!;
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, '#0c2016');
  bg.addColorStop(1, '#06120c');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  ctx.fillStyle = AMBER;
  ctx.font = "64px 'Doto', monospace";
  ctx.fillText('ARCHIE', 80, 130);
  const gap = ctx.measureText('ARCHIE ').width; // misurata con il carattere LED, prima di cambiarlo
  ctx.fillStyle = TEXT;
  ctx.font = "64px 'Bebas Neue', sans-serif";
  ctx.fillText('BET', 80 + gap, 130);

  ctx.fillStyle = TEXT;
  ctx.font = "88px 'Bebas Neue', sans-serif";
  ctx.fillText(s.title.toUpperCase(), 80, 250);
  ctx.fillStyle = MUTED;
  ctx.font = "34px 'Barlow', sans-serif";
  const day = new Date(`${s.period}T12:00:00`).toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' });
  ctx.fillText(day, 80, 305);

  let y = 400;
  const legs = s.legs.slice(0, 7);
  for (const l of legs) {
    ctx.fillStyle = MUTED;
    ctx.font = "30px 'Barlow', sans-serif";
    ctx.fillText(`${l.home} – ${l.away}`, 80, y);
    ctx.fillStyle = l.status === 'won' ? '#4fd18b' : l.status === 'lost' ? '#ff5d52' : AMBER;
    ctx.font = "bold 40px 'Barlow', sans-serif";
    const event = l.event.charAt(0).toUpperCase() + l.event.slice(1);
    const rows = lines(ctx, event, W - 360);
    rows.forEach((r, i) => ctx.fillText(r, 80, y + 48 + i * 46));
    ctx.fillStyle = TEXT;
    ctx.font = "44px 'Doto', monospace";
    const p = `${Math.round(l.p * 100)}%`;
    ctx.fillText(p, W - 80 - ctx.measureText(p).width, y + 48);
    y += 70 + rows.length * 46;
  }
  if (s.legs.length > legs.length) {
    ctx.fillStyle = MUTED;
    ctx.font = "30px 'Barlow', sans-serif";
    ctx.fillText(`+ altri ${s.legs.length - legs.length} pronostici nell'app`, 80, y);
  }

  ctx.fillStyle = 'rgba(255, 198, 26, 0.12)';
  ctx.fillRect(0, H - 230, W, 230);
  ctx.fillStyle = TEXT;
  ctx.font = "44px 'Bebas Neue', sans-serif";
  const summary = s.singles
    ? `${s.legs.length} occasioni da giocare singole`
    : s.system
      ? `Sistema ${s.system} su ${s.legs.length} · incassi il ${Math.round(s.win_probability * 100)}% delle volte`
      : `Quota ${s.total_odds.toFixed(2)} · esce 1 volta su ${Math.max(1, Math.round(1 / s.win_probability))}`;
  ctx.fillText(summary, 80, H - 140);
  ctx.fillStyle = MUTED;
  ctx.font = "28px 'Barlow', sans-serif";
  ctx.fillText('Probabilità studiate da Archie, non certezze · Gioca responsabilmente · 18+', 80, H - 80);

  return new Promise((resolve) => canvas.toBlob((b) => resolve(b!), 'image/png'));
}

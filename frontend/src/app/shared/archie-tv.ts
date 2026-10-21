import { httpResource } from '@angular/common/http';
import { Component, computed, inject, input, signal } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ago } from '../core/format';

interface Video {
  video_id: string;
  title: string;
  channel: string;
  published: string;
  thumbnail: string;
}

/** ArchieTV (D129): ultimi video dei canali ufficiali delle leghe, guardabili qui con il lettore di YouTube. */
@Component({
  selector: 'ab-archie-tv',
  template: `
    <section class="panel tv" aria-labelledby="tv-title">
      <div class="tv-head">
        <h2 id="tv-title" class="tv-title"><span class="led">ARCHIE</span><span class="title"> TV</span></h2>
        <div class="chips" role="group" aria-label="Canale">
          @for (c of channels(); track c) {
            <button type="button" class="chip" [class.on]="channel() === c" [attr.aria-pressed]="channel() === c" (click)="channel.set(c)">{{ c }}</button>
          }
        </div>
      </div>
      @if (playing(); as url) {
        <div class="player">
          <iframe [src]="url" title="Video" allow="accelerometer; autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>
          <button type="button" class="close" (click)="current.set(null)">Chiudi</button>
        </div>
      }
      <div class="grid">
        @for (v of shown(); track v.video_id) {
          <button type="button" class="video" [class.on]="current() === v.video_id" (click)="current.set(v.video_id)">
            <img [src]="v.thumbnail" alt="" loading="lazy" />
            <span class="v-title">{{ v.title }}</span>
            <span class="muted small">{{ v.channel }} · {{ ago(v.published) }}</span>
          </button>
        } @empty {
          <p class="muted small">{{ videos.isLoading() ? 'Carico i video…' : 'Nessun video: i canali YouTube non rispondono, riprova più tardi.' }}</p>
        }
      </div>
      <p class="muted small">Video ufficiali dai canali YouTube di Serie A, Premier League, LaLiga, Bundesliga, Ligue 1 e UEFA. Serie B e C non hanno un canale ufficiale con video pubblici.</p>
    </section>
  `,
  styles: `
    .tv { padding: 10px 12px; }
    .tv-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
    .tv-title { margin: 0; font-size: 20px; }
    .tv-title .title { color: var(--text); }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip { padding: 4px 10px; font: inherit; font-size: 13px; color: var(--text-2); background: transparent; border: 1px solid var(--line-strong); border-radius: 999px; cursor: pointer; }
    .chip.on { color: var(--bg); background: var(--amber); border-color: var(--amber); }
    .player { position: relative; margin-bottom: 12px; aspect-ratio: 16 / 9; max-height: 520px; }
    .player iframe { width: 100%; height: 100%; border: 0; border-radius: 8px; }
    .close { position: absolute; top: 8px; right: 8px; padding: 4px 10px; font: inherit; color: var(--text); background: rgba(0, 0, 0, 0.7); border: 1px solid var(--line-strong); border-radius: 4px; cursor: pointer; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 12px; }
    .video { display: flex; flex-direction: column; gap: 4px; padding: 0; text-align: left; font: inherit; color: var(--text); background: none; border: 0; cursor: pointer; }
    .video img { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; border-radius: 6px; border: 2px solid transparent; }
    .video:hover img, .video.on img { border-color: var(--amber); }
    .v-title { font-weight: 600; line-height: 1.25; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  `,
})
export class ArchieTv {
  private readonly sanitizer = inject(DomSanitizer);
  readonly limit = input(8);
  protected readonly ago = ago;
  protected readonly videos = httpResource<Video[]>(() => '/api/tv', { defaultValue: [] });
  protected readonly channel = signal('Tutti');
  protected readonly current = signal<string | null>(null);
  protected readonly channels = computed(() => ['Tutti', ...new Set(this.videos.value().map((v) => v.channel))]);
  protected readonly shown = computed(() =>
    this.videos
      .value()
      .filter((v) => this.channel() === 'Tutti' || v.channel === this.channel())
      .slice(0, this.limit()),
  );
  /** Lettore ufficiale di YouTube in modalità privacy avanzata (niente cookie finché non si guarda) */
  protected readonly playing = computed<SafeResourceUrl | null>(() => {
    const id = this.current();
    return id ? this.sanitizer.bypassSecurityTrustResourceUrl(`https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}?autoplay=1`) : null;
  });
}

/** Disegna Archie in 3D su un canvas trasparente e lo anima: ali che sbattono (in volo), testa che si gira
 *  un poco, palpebre che sbattono ogni tanto. Si carica solo quando serve (three.js è pesante). */
import { ACESFilmicToneMapping, AmbientLight, DirectionalLight, PMREMGenerator, PerspectiveCamera, SRGBColorSpace, Scene, WebGLRenderer } from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { OwlParts, buildOwl } from './owl-model';

export type OwlPose = 'fly' | 'idle';

export class OwlView {
  private readonly renderer: WebGLRenderer;
  private readonly scene = new Scene();
  private readonly camera = new PerspectiveCamera(28, 1, 0.1, 50);
  private readonly owl: OwlParts;
  private frame = 0;
  private readonly start = performance.now();
  private readonly resize = new ResizeObserver(() => this.fit());

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly pose: OwlPose,
    private readonly animate = true,
  ) {
    this.renderer = new WebGLRenderer({ canvas, alpha: true, antialias: true, preserveDrawingBuffer: !animate });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.outputColorSpace = SRGBColorSpace;
    this.renderer.toneMapping = ACESFilmicToneMapping;
    const pmrem = new PMREMGenerator(this.renderer);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture; // riflessi del metallo
    pmrem.dispose();
    this.scene.add(new AmbientLight(0xffffff, 0.25));
    const key = new DirectionalLight(0xffe2c0, 2.2);
    key.position.set(2.5, 3, 4);
    const rim = new DirectionalLight(0x6f8cff, 1.4);
    rim.position.set(-3, 1.5, -2.5);
    this.scene.add(key, rim);
    this.owl = buildOwl();
    this.scene.add(this.owl.root);
    this.camera.position.set(0, 0.3, 5.3); // il gufo riempie quasi tutto il riquadro
    this.camera.lookAt(0, 0.1, 0);
    this.fit();
    this.resize.observe(canvas);
    if (animate) this.frame = requestAnimationFrame((t) => this.tick(t));
    else this.draw(0);
  }

  destroy(): void {
    cancelAnimationFrame(this.frame);
    this.resize.disconnect();
    this.renderer.dispose();
  }

  /** Disegna l'istante t (ms dall'inizio): serve anche per le foto ferme */
  draw(t: number): void {
    const { wings, lids, head, root } = this.owl;
    const s = t / 1000;
    const flap = this.pose === 'fly' ? Math.sin(s * 2 * Math.PI * 2.4) * 0.65 : Math.sin(s * 1.3) * 0.05;
    wings[0].rotation.z = -0.15 - flap;
    wings[1].rotation.z = 0.15 + flap;
    root.position.y = this.pose === 'fly' ? Math.sin(s * 2 * Math.PI * 1.2) * 0.06 : 0;
    head.rotation.y = Math.sin(s * 0.7) * 0.18;
    head.rotation.z = Math.sin(s * 0.45) * 0.04;
    const blink = s % 4.2 < 0.14 ? 1.8 : 1; // ogni 4 secondi le palpebre scendono
    for (const lid of lids) lid.scale.y = blink;
    this.renderer.render(this.scene, this.camera);
  }

  private tick(now: number): void {
    this.draw(now - this.start);
    this.frame = requestAnimationFrame((t) => this.tick(t));
  }

  private fit(): void {
    const w = this.canvas.clientWidth || 200;
    const h = this.canvas.clientHeight || 200;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    if (!this.animate) this.draw(0);
  }
}

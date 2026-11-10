/** Archie in 3D (D193): gufo meccanico in ottone e rame con patina verderame, occhiali a ingranaggio e
 *  sguardo serio e furbo (palpebre calate e oblique, sopracciglia a V, la sinistra un po' più bassa).
 *  Solo geometria di three.js: niente modelli da scaricare. Le parti che si muovono sono restituite a parte. */
import {
  ConeGeometry, CylinderGeometry, ExtrudeGeometry, Group, Mesh, MeshStandardMaterial, Object3D, Shape, SphereGeometry, TorusGeometry,
} from 'three'; // prettier-ignore

export interface OwlParts {
  root: Group;
  /** perno delle ali (spalla): ruotano attorno a z per sbattere */
  wings: [Object3D, Object3D];
  /** palpebre: si abbassano per sbattere le palpebre */
  lids: [Object3D, Object3D];
  pupils: [Object3D, Object3D];
  head: Object3D;
}

/** Numeri pseudo-casuali ripetibili: la patina esce sempre uguale */
export function seeded(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

/** Punto sulla superficie di un ellissoide (centro c, semiassi r) nella direzione (theta, phi) */
export function onEllipsoid(c: [number, number, number], r: [number, number, number], theta: number, phi: number): [number, number, number] {
  return [c[0] + r[0] * Math.sin(phi) * Math.cos(theta), c[1] + r[1] * Math.cos(phi), c[2] + r[2] * Math.sin(phi) * Math.sin(theta)];
}

/** Palpebra piatta: la parte di cerchio (raggio r) sopra la corda, alta `cover` dalla cima; origine in cima al cerchio */
export function lidGeometry(r: number, cover: number): ExtrudeGeometry {
  const y = r - cover; // altezza della corda rispetto al centro
  const a = Math.asin(Math.max(-1, Math.min(1, y / r)));
  const shape = new Shape();
  shape.moveTo(r * Math.cos(a), y - r);
  shape.absarc(0, -r, r, a, Math.PI - a, false);
  shape.lineTo(r * Math.cos(a), y - r);
  return new ExtrudeGeometry(shape, { depth: 0.03, bevelEnabled: true, bevelSize: 0.012, bevelThickness: 0.012, bevelSegments: 3, curveSegments: 32 });
}

export function buildOwl(): OwlParts {
  const brass = new MeshStandardMaterial({ color: 0xc08a35, metalness: 1, roughness: 0.32 });
  const copper = new MeshStandardMaterial({ color: 0xb4623a, metalness: 1, roughness: 0.38 });
  const patina = new MeshStandardMaterial({ color: 0x2f6e60, metalness: 0.3, roughness: 0.85 });
  const iron = new MeshStandardMaterial({ color: 0x2b2420, metalness: 0.8, roughness: 0.5 });
  const iris = new MeshStandardMaterial({ color: 0xff6a00, emissive: 0xff5200, emissiveIntensity: 0.55, metalness: 0, roughness: 0.4 });
  const lidMetal = new MeshStandardMaterial({ color: 0x8c4a28, metalness: 0.9, roughness: 0.42 });
  const black = new MeshStandardMaterial({ color: 0x0a0806, roughness: 0.2 });

  const root = new Group();
  const add = (parent: Object3D, mesh: Mesh, x = 0, y = 0, z = 0) => {
    mesh.position.set(x, y, z);
    parent.add(mesh);
    return mesh;
  };

  // Corpo a uovo
  const bodyC: [number, number, number] = [0, -0.05, 0];
  const bodyR: [number, number, number] = [0.8, 0.9, 0.72];
  const body = add(root, new Mesh(new SphereGeometry(1, 48, 32), copper), ...bodyC);
  body.scale.set(...bodyR);

  // Testa grande, un po' larga
  const head = new Group();
  head.position.set(0, 0.92, 0.02);
  root.add(head);
  const skull = add(head, new Mesh(new SphereGeometry(1, 48, 32), brass));
  skull.scale.set(0.7, 0.58, 0.62);

  // Patina verderame qua e là (come nello screenshot)
  const rnd = seeded(7);
  for (let i = 0; i < 9; i++) {
    const theta = Math.PI * (0.15 + 0.7 * rnd()) + (rnd() < 0.3 ? Math.PI : 0);
    const phi = Math.PI * (0.25 + 0.6 * rnd());
    const p = onEllipsoid(bodyC, bodyR, theta, phi);
    const spot = add(root, new Mesh(new SphereGeometry(0.06 + 0.06 * rnd(), 16, 12), patina), ...p);
    spot.scale.set(1, 0.7, 0.2);
    spot.lookAt(p[0] * 3, p[1] * 3 - bodyC[1] * 2, p[2] * 3);
  }

  // Placca sul petto con la spirale
  const plate = add(root, new Mesh(new CylinderGeometry(0.4, 0.4, 0.05, 48), patina), 0, -0.12, 0.66);
  plate.rotation.x = Math.PI / 2 - 0.12;
  for (let i = 0; i < 4; i++) {
    const ring = add(root, new Mesh(new TorusGeometry(0.34 - i * 0.08, 0.022, 10, 48), i % 2 ? brass : copper), 0, -0.12, 0.7 + i * 0.006);
    ring.rotation.x = -0.12;
  }
  for (let i = 0; i < 10; i++) {
    const a = (i / 10) * Math.PI * 2;
    add(root, new Mesh(new SphereGeometry(0.028, 10, 8), brass), Math.cos(a) * 0.44, -0.12 + Math.sin(a) * 0.44, 0.66 - Math.sin(a) * 0.05);
  }

  // Ciuffi delle orecchie, all'indietro e in fuori
  for (const s of [-1, 1]) {
    const tuft = add(head, new Mesh(new ConeGeometry(0.11, 0.42, 16), copper), s * 0.42, 0.5, -0.05);
    tuft.rotation.z = -s * 0.55;
    tuft.rotation.x = -0.25;
  }

  // Occhiali a ingranaggio: cornice, fondo scuro, iride arancio, pupilla
  const pupils: Object3D[] = [];
  const lids: Object3D[] = [];
  for (const s of [-1, 1]) {
    const eye = new Group();
    eye.position.set(s * 0.27, 0.02, 0.5);
    head.add(eye);
    add(eye, new Mesh(new TorusGeometry(0.21, 0.055, 14, 40), brass));
    for (let i = 0; i < 12; i++) {
      // denti dell'ingranaggio
      const a = (i / 12) * Math.PI * 2;
      const tooth = add(eye, new Mesh(new CylinderGeometry(0.03, 0.03, 0.06, 8), brass), Math.cos(a) * 0.27, Math.sin(a) * 0.27, -0.01);
      tooth.rotation.x = Math.PI / 2;
    }
    const back = add(eye, new Mesh(new CylinderGeometry(0.2, 0.2, 0.04, 32), iron), 0, 0, -0.03);
    back.rotation.x = Math.PI / 2;
    const ir = add(eye, new Mesh(new SphereGeometry(0.16, 32, 24), iris), 0, 0, 0.0);
    ir.scale.z = 0.45;
    const pupil = add(eye, new Mesh(new SphereGeometry(0.065, 20, 16), black), 0.035, -0.02, 0.07); // guarda di lato: furbo
    pupil.scale.z = 0.5;
    pupils.push(pupil);

    // Palpebra: lamina che copre la parte alta dell'occhio, inclinata (angolo interno più basso = serio);
    // la sinistra più calata dell'altra: occhio socchiuso, sguardo furbo
    const lidPivot = new Group();
    lidPivot.rotation.z = s * 0.3;
    lidPivot.position.set(0, 0, 0.075);
    eye.add(lidPivot);
    const lid = new Mesh(lidGeometry(0.19, s < 0 ? 0.2 : 0.15), lidMetal);
    lid.position.y = 0.19; // il perno è in cima all'occhio: allungando la lamina verso il basso l'occhio si chiude
    lidPivot.add(lid);
    lids.push(lid);

    // Sopracciglio a V
    const brow = add(eye, new Mesh(new CylinderGeometry(0.05, 0.035, 0.42, 12), iron), -s * 0.02, 0.24, 0.08);
    brow.rotation.z = Math.PI / 2 + s * 0.42;
  }

  // Becco piccolo, verso il basso
  const beak = add(head, new Mesh(new ConeGeometry(0.075, 0.24, 20), brass), 0, -0.12, 0.6);
  beak.rotation.x = Math.PI - 0.35;

  // Ali con lo scudo rotondo, appese alla spalla
  const wings: Object3D[] = [];
  for (const s of [-1, 1]) {
    const pivot = new Group();
    pivot.position.set(s * 0.7, 0.35, -0.02);
    root.add(pivot);
    const wing = add(pivot, new Mesh(new SphereGeometry(1, 32, 20), brass), s * 0.1, -0.42, 0);
    wing.scale.set(0.16, 0.55, 0.42);
    const shield = add(pivot, new Mesh(new CylinderGeometry(0.3, 0.3, 0.07, 40), copper), s * 0.24, -0.4, 0.02);
    shield.rotation.z = Math.PI / 2;
    const rim = add(pivot, new Mesh(new TorusGeometry(0.3, 0.03, 10, 40), brass), s * 0.28, -0.4, 0.02);
    rim.rotation.y = Math.PI / 2;
    add(pivot, new Mesh(new SphereGeometry(0.07, 16, 12), patina), s * 0.29, -0.4, 0.02);
    wings.push(pivot);
  }

  // Zampe e artigli
  for (const s of [-1, 1]) {
    add(root, new Mesh(new CylinderGeometry(0.06, 0.07, 0.32, 12), iron), s * 0.26, -0.98, 0.12);
    for (const a of [-0.45, 0, 0.45]) {
      const claw = add(root, new Mesh(new ConeGeometry(0.035, 0.2, 10), brass), s * 0.26 + Math.sin(a) * 0.08, -1.13, 0.2 + Math.cos(a) * 0.06);
      claw.rotation.x = Math.PI / 2;
      claw.rotation.y = a;
    }
  }

  return { root, wings: wings as [Object3D, Object3D], lids: lids as [Object3D, Object3D], pupils: pupils as [Object3D, Object3D], head };
}

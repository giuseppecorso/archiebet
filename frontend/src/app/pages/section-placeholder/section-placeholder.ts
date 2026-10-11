import { Component, input } from '@angular/core';
import { Section } from '../../core/sections';

/** Pagina provvisoria di una sezione: dice cosa conterrà e in quale fase arriva. */
@Component({
  selector: 'ab-section-placeholder',
  templateUrl: './section-placeholder.html',
  styleUrl: './section-placeholder.scss',
})
export class SectionPlaceholder {
  /** Arriva dai dati della rotta (withComponentInputBinding) */
  readonly section = input.required<Section>();
}

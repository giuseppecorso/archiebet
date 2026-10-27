import { Component, computed, input } from '@angular/core';
import { PRONOSTICI_TABS } from '../../core/sections';
import { Subnav } from '../../shared/subnav';
import { Radar } from '../radar/radar';
import { Daily } from '../daily/daily';
import { Generator } from './generator';

type Tab = 'daily' | 'multipla' | 'occasioni';

/** Pronostici: la bacheca Daily (scheda principale), "Fammi una multipla" e Occasioni. */
@Component({
  selector: 'ab-picks',
  imports: [Radar, Generator, Subnav, Daily],
  templateUrl: './picks.html',
})
export class Picks {
  /** Dall'indirizzo: ?tab=occasioni */
  readonly tabParam = input<string | undefined>(undefined, { alias: 'tab' });
  protected readonly tabs = PRONOSTICI_TABS;
  protected readonly tab = computed<Tab>(() => (this.tabParam() === 'occasioni' ? 'occasioni' : this.tabParam() === 'multipla' ? 'multipla' : 'daily'));
}

import { Component, computed, input } from '@angular/core';
import { PRONOSTICI_TABS } from '../../core/sections';
import { Subnav } from '../../shared/subnav';
import { Radar } from '../radar/radar';
import { Daily } from '../daily/daily';
import { Generator } from './generator';
import { Strategies } from './strategies';

type Tab = 'daily' | 'multipla' | 'occasioni' | 'strategie';

/** Pronostici: la bacheca Daily (scheda principale), "Fammi una multipla", Occasioni e Strategie (D194). */
@Component({
  selector: 'ab-picks',
  imports: [Radar, Generator, Subnav, Daily, Strategies],
  templateUrl: './picks.html',
})
export class Picks {
  /** Dall'indirizzo: ?tab=occasioni */
  readonly tabParam = input<string | undefined>(undefined, { alias: 'tab' });
  protected readonly tabs = PRONOSTICI_TABS;
  protected readonly tab = computed<Tab>(() => {
    const t = this.tabParam();
    return t === 'occasioni' || t === 'multipla' || t === 'strategie' ? t : 'daily';
  });
}

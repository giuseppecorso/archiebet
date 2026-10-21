import { Component } from '@angular/core';
import { MIO_ARCHIE_TABS } from '../../core/sections';
import { AskArchie } from '../../shared/ask-archie';
import { Subnav } from '../../shared/subnav';

/** Il mio Archie · Chiedi ad Archie: domande in italiano su partite, occasioni, notizie e le tue giocate (D112). */
@Component({
  selector: 'ab-ask-page',
  imports: [AskArchie, Subnav],
  template: `
    <ab-subnav [items]="tabs" label="Il mio Archie" />
    <ab-ask-archie placeholder="Es. Come arriva il Bari a domenica? Dove sto perdendo soldi?" />
  `,
})
export class AskPage {
  protected readonly tabs = MIO_ARCHIE_TABS;
}

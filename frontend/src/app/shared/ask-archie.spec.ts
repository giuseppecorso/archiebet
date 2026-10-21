import { answerHtml } from './ask-archie';

describe('answerHtml', () => {
  it('rende grassetti ed elenchi e non lascia passare HTML', () => {
    const html = answerHtml('**Niente valore.**\n- Over 8,5 al 54%\n- 12 a 1,32\n<script>x</script>');
    expect(html).toBe('<p><strong>Niente valore.</strong></p><ul><li>Over 8,5 al 54%</li><li>12 a 1,32</li></ul><p>&lt;script&gt;x&lt;/script&gt;</p>');
  });
});

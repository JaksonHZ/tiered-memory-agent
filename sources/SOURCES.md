# Fontes

Textos oficiais a partir dos quais `scripts/build_semantic.py` gera a árvore `semantic/`. Os arquivos estão como foram
baixados.

| Arquivo | Norma | URL | Baixado em | SHA-256 |
|---|---|---|---|---|
| `rdc-216-2004.html` | RDC ANVISA nº 216, de 15/09/2004 | https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2004/res0216_15_09_2004.html | 2026-10-27 | `35eb00b056cf218456883e5653b5e807be0520b54cf412f631f924d8dc6925cf` |
| `rdc-275-2002.html` | RDC ANVISA nº 275, de 21/10/2002 | https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2002/rdc0275_21_10_2002.html | 2026-10-27 | `f017afcc545fea97ecdeb2489b2b108227ecf32bc67a40149080ca6772770bc1` |
| `portaria-cvs-3-2026.pdf` | Portaria CVS nº 3, de 03/07/2026 (SP), texto republicado no DOE-SP de 28/09/2026 | https://apicvs.saude.sp.gov.br/download/e_pt-cvs-3_030726-rep-280926.pdf | 2026-10-27 | `04eb8ddbf5f4efa21215f483997e771a080e2d1f1f31c021973490371a43cbbe` |
| `portaria-cvs-9-2026.pdf` | Portaria CVS nº 9, de 05/10/2026 (SP), DOE-SP de 05/10/2026 | https://apicvs.saude.sp.gov.br/download/e_pt-cvs-9_051026.pdf | 2026-10-27 | `bfdbc770d86602b0f5716ff590b28f1dcbacd8fe2c4952bcbbc96ff4aacb8807` |

## Notas

- As duas RDCs vêm do Saúde Legis, o sistema de legislação do Ministério da Saúde. A própria página avisa que o texto
  não substitui o publicado no Diário Oficial da União. Nenhuma das duas páginas traz nota de alteração ou revogação
  (conferido em 2026-10-27).
- A página da RDC 275/2002 traz o texto duas vezes (original e republicação no DOU de 06/11/2002); o build usa a
  primeira. O Anexo II (lista de verificação para a indústria de alimentos) não está no texto da página e ficou de fora.
- As duas portarias vêm do site do Centro de Vigilância Sanitária de São Paulo (https://cvs.saude.sp.gov.br/Legislacao),
  que serve os PDFs do Diário Oficial do Estado pela URL da tabela.
- A Portaria CVS 3/2026 substitui a Portaria CVS 5/2013, que fica fora do corpus. O texto usado é a republicação de
  28/09/2026, que, segundo a nota no fim dela, atualiza o texto de 06/07/2026 e inclui o Anexo II (alergênicos). O Anexo
  I, um modelo de cartaz, é imagem no PDF e ficou de fora.
- A Portaria CVS 9/2026 muda os arts. 3º e 4º da CVS 3/2026: a vigência da CVS 3 e a revogação da CVS 5 passam para
  01/02/2027. O arquivo da CVS 3 em `semantic/` traz a redação original desses artigos; a nova está em
  `semantic/scope-and-definitions/cvs-9-2026.md`.
- Para reconstruir a árvore a partir dos PDFs é preciso o `pdftotext` (pacote poppler-utils).

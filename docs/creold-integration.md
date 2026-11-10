# Creold în Illona 0.4.1

Sursă: [Sergey Osokin / creold/illustrator-scripts](https://github.com/creold/illustrator-scripts/tree/9b3e3eeade9ba748f41612ec4697bb6a5c2489c2). Biblioteca gratuită MIT este inclusă local la commitul `9b3e3eeade9ba748f41612ec4697bb6a5c2489c2`: **104 scripturi JSX**, două arhive și trei fișiere auxiliare. Nu este necesară descărcarea lor la fiecare utilizare. Licența și antetele originale sunt păstrate.

## Cele patru instrumente

| Instrument | Rol |
| --- | --- |
| `illona_creold_catalog` | Caută după nume/descriere și categorie. |
| `illona_creold_script_info` | Citește versiunea, sursa, dependențele, dialogurile și sfera operației. |
| `illona_creold_run_script` | Lansează un original fix din catalog, pe documentul și selecția explicite. |
| `illona_creold_action` | Execută una dintre cele 14 adaptări cu parametri direcți, fără dialog. |

Serverul are acum **86 de instrumente MCP**: 16 Illona, 66 Pro și patru Creold. Cele 104 scripturi și cele 14 acțiuni sunt opțiuni ale acestor instrumente, nu încă 117 instrumente separate. Resursa `illona://creold-guide` este consultabilă de clientul AI.

## Adaptări cu parametri direcți

| Acțiune | Utilitate și opțiuni principale |
| --- | --- |
| `reverse_gradient_colors` | Inversează culorile și opacitățile stopurilor; `target`: fill/stroke/both. |
| `distribute_gradient_stops` | Distribuie uniform între capetele existente. |
| `remove_gradient_stops` | Păstrează numai cele două stopuri de capăt. |
| `cycle_gradient_colors` | Rotește culorile; `steps` pozitiv/negativ, pozițiile și opacitățile rămân fixe. |
| `stroke_color_from_fill` | Contur derivat din umplere; `shift_percent`, `width_pt`. |
| `average_stroke_width` | Normalizează grosimea contururilor la medie; `precision`. |
| `align_text_baselines` | Aliniază point text pe baseline; `baseline_y_pt` sau `reference_uuid`, `spacing_pt`. |
| `round_coordinates` | Rotunjește poziția, fără scalare; `step_pt`, `reference`, `include_stroke`. |
| `set_point_coordinates` | Mută ancore și mânere împreună; `point_indices`, `x_pt`, `y_pt`, `relative`. |
| `transform_points` | Scalează, rotește și deplasează punctele Bézier; origine explicită opțională. |
| `draw_artboard_rectangles` | Creează dreptunghiuri pentru artboardurile explicite, cu `bleed_pt`, strat și culori. |
| `change_opacity` | Opacitate absolută, diferență sau factor; `mode`, `value`. |
| `trace_images` | Vectorizează PlacedItem/RasterItem printr-un preset Illustrator instalat, extinde traseele și verifică absența rasterelor; `preset`, `ignore_white`. |
| `average_colors` | Media umplerilor/contururilor în aceeași familie RGB/CMYK/Gray; metodă arithmetic sau RMS. |

Toată geometria folosește **puncte native ale documentului, Y în sus**. Indicii punctelor și artboardurilor încep de la zero. Sunt acceptate maximum 500 UUID-uri și 5.000 puncte procesate. Opțiunile nerelevante acțiunii sunt respinse înainte de modificare. Baseline-urile acceptă point text; culorile spot sunt convertite în culoarea de proces pentru mediere. Degradeurile editate primesc definiții izolate, păstrând obiectele neselectate care foloseau definiția inițială.

Exemplu de cerere pentru opacitate:

```json
{"document_id":"ID din illona_status","action":"change_opacity","object_ids":["UUID inspectat"],"options":{"mode":"absolute","value":75},"operation_id":"opacitate-v1"}
```

## Originale cu dialog

1. Citește `script_info` și inspectează documentul/UUID-urile.
2. Trimite `run_script` cu ID-ul exact din catalog și `mode="interactive"`.
3. Rezultatul `queued` înseamnă că fereastra originală urmează să fie utilizată în Illustrator. Completează și confirmă dialogul sau anulează-l.
4. Cere `illona_operation_status` cu același `operation_id`. Nu lansa altă editare cât operația este în așteptare.
5. Inspectează și previzualizează artwork-ul înainte de a afirma că modificarea este corectă.

Lansarea folosește un proces separat pentru a putea returna imediat. Dialogul poate rămâne deschis maximum o oră. Un timeout nu anulează garantat execuția nativă. O fereastră modeless rămasă deschisă după întoarcerea scriptului este închisă și raportată. Nu există panou persistent pentru originale precum DocumentSwitcher.

Numai cinci originale acceptă `mode="automatic"`: `CycleGradientBackward`, `CycleGradientForward`, `CycleGradientRandom`, `DistributeGradientStops`, `RemoveGradientStops`. Cer UUID-uri explicite. Originalele de gradient pot modifica definiții partajate; preferă adaptările pentru editarea izolată.

`script_returned` înseamnă că originalul a întors controlul. Originalele pot prinde intern erori sau pot fi anulate, astfel încât acest rezultat are întotdeauna `modification_verified=false`. Eșecurile parțiale ale adaptărilor păstrează diagnosticul și sunt raportate drept erori MCP.

## Protecții și limite

Illona acceptă numai ID-uri fixe din catalog, verifică SHA-256 pentru sursă și fișiere auxiliare, validează documentul/UUID-urile și serializează execuția. Nu acceptă JSX sau căi arbitrare pentru execuție. Preferințele native identificate, originea riglelor, sistemul de coordonate și nivelul interacțiunii sunt restaurate după original.

Setările scripturilor sunt redirecționate în `output/creold/settings`. Selectoarele de export și operațiile de scriere identificate sunt limitate la directorul de rezultate sau la operația locală. Această adaptare a surselor fixe nu este un sandbox universal pentru ExtendScript; metadatele statice nu dovedesc siguranța fiecărui flux posibil. Inspecția căilor native nu certifică toate cazurile de aliasuri și legături simbolice.

Scripturile cu efect asupra aplicației, mai multor documente sau fișierelor necesită `application_scope=true`; acest parametru desemnează explicit sfera cerută. Nu se scriu documente salvate în afara directorului Illona. Unele originale folosesc undo, actions, setări, fonturi, selecția punctelor sau resurse partajate: citește informațiile scriptului înainte de folosire.

Cererea și rezultatul sunt păstrate în `.illona-state/jobs`. Pentru o operație întreruptă, folosește același ID. Dacă rezultatul nativ există iar procesul interactiv nu a finalizat înregistrarea principală, reluarea aceleiași cereri reconstruiește rezultatul fără să ruleze originalul din nou.

## Verificare

Testele offline verifică schemele, catalogul MCP, hash-urile, serializarea și recuperarea operațiilor, geometria și simulări ale DOM-ului Adobe. Testele nu pornesc Illustrator.

Rezultatele native și calitatea vizuală trebuie verificate pe instalarea și fișierele utilizatorului. Trasarea fotografiilor este o aproximație vectorială; detaliile nu sunt reconstruite dincolo de sursa originală. Extinderea poate schimba limitele dacă se ignoră marginile albe. Nu repeta o trasare cu rezultat incert.

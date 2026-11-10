"""Original Illona practice procedures, grounded in linked Adobe tutorials.

This is retrieved guidance, not model training, copied tutorial content, or a
claim that Illustrator's complete user interface is exposed through scripting.
"""

PLAYBOOK = """Illona — bibliotecă de practică Illustrator
Revizuit: 2026-11-09. Procedurile sunt instrucțiuni reutilizabile, nu modificări ale modelului AI.
Ghid general de practică pentru ilustrații, logo-uri, tipografie și broșuri. Nu conține conversații, lucrări sau evaluări personale.

SURSE OFICIALE
Catalog de lecții: https://www.adobe.com/uk/learn/illustrator
Logo din schiță: https://www.adobe.com/uk/learn/illustrator/web/create-logo-from-sketch
Flyer tipografic: https://www.adobe.com/uk/learn/illustrator/web/typographic-flyer-design
Aliniere: https://www.adobe.com/uk/learn/illustrator/web/snapping-for-perfect-alignment
Gradienți: https://www.adobe.com/uk/learn/illustrator/web/color-gradients
Aceste proceduri sunt formulate pentru Illona; nu reproduc integral lecții, clipuri sau materialele lor de exercițiu.

MOD DE LUCRU
1. Identifică rezultatul cerut, publicul, mesajul principal, formatul, textul exact și referințele vizuale. Cere doar informațiile care blochează lucrarea; pentru alegeri reversibile folosește ipoteze explicite și continuă.
2. Consultă illona_status, obține document_id și inspectează înainte de editare. Planifică artboardurile, straturile, ordinea de citire, dimensiunile, paleta și tipografia.
3. Construiește o compoziție editabilă prin instrumentele disponibile. Verifică fonturile instalate. Păstrează diacriticele și textul editabil. Grupează elementele după rol, cu nume utile.
4. Cere illona_preview_document după fiecare etapă vizuală importantă. Inspectează imaginea; un răspuns de succes al instrumentului nu demonstrează că layoutul este bun.
5. Evaluează separat geometria, lizibilitatea și direcția vizuală. Corectează problema observată și compară aceeași vedere înainte/după. Rulează preflight-ul relevant și păstrează limitele verificărilor.
6. Salvează sursa AI și exporturile necesare. Pentru preferințe viitoare, diferențiază aprobarea explicită a utilizatorului de presupunerile agentului. Un exemplu sau feedback care rămâne doar în conversație nu devine automat memorie globală; trebuie păstrat în proiect și consultat în sesiunile următoare.

REGULI DE EXECUȚIE
Instrumentele originale Illona folosesc implicit mm și text poziționat după cadrul geometric. Instrumentele illona_pro_ folosesc puncte; point text are Y la baseline, area text are Y la muchia de sus. Nu amesteca unitățile.
Folosește UUID-urile native și document_id explicit. target_artboard selectează temporar planșa pentru instrumentele avansate. Folosește un operation_id stabil, recuperează rezultatele după întrerupere și nu repeta o operație ambiguă sub alt ID.

MODUL 1 — FORME ȘI CURBE
Exercițiu original: un badge simplu, cu siluetă recognoscibilă și versiune monocromă.
Aplică illona_pro_create_rectangle, create_ellipse și create_path pentru forme și Bézier, apoi group_objects și modify_object pentru organizare și ajustări. Lucrează cu puține ancore și mânere coerente; verifică vizual curbele și spațiile negative la dimensiunea de utilizare.
Criterii: contururi intenționate, elemente editabile, forme închise unde este necesar, versiune monocromă lizibilă, fără coliziuni accidentale.
Limită: Pathfinder Divide/Unite nu are un instrument public în această versiune. Construirea contururilor finale direct nu este un înlocuitor general pentru operații booleene.

MODUL 2 — TIPOGRAFIE ȘI LAYOUT
Exercițiu original: flyer A4 sau pagină de broșură cu titlu, text și contact.
Stabilește grila și ierarhia înainte de plasare. Folosește illona_pro_create_text_frame pentru area/point text, leading și tracking explicite când sunt necesare, illona_pro_apply_text_style pentru stiluri existente și illona_pro_align_objects pentru relații geometrice.
Criterii: text exact, diacritice prezente, contrast lizibil, ierarhie clară, spațieri repetabile și casete încadrate după inspecție vizuală. Verificarea automată nu certifică absența textului ascuns.
Limită: Retype, activarea Adobe Fonts și crearea/editarea definițiilor stilurilor tipografice nu sunt instrumente publice ale versiunii curente.

MODUL 3 — ALINIERE ȘI RITM
Exercițiu original: trei carduri cu titlu, pictogramă și descriere pe aceeași planșă.
Folosește illona_pro_align_objects, duplicate_objects, modify_object și convert_coordinate. Verifică valorile numerice ale limitelor și apoi aspectul optic în preview, mai ales pentru text.
Criterii: margini constante, distribuție consecventă, aceeași unitate de măsură și aliniere optică verificată. Alinierea casetelor nu garantează alinierea vizuală a literelor.
Limită: Snap to Glyphs, snapping interactiv de ancore și comenzile Smart Guides nu sunt expuse aici.

MODUL 4 — CULOARE ȘI VOLUM
Exercițiu original: ilustrație cu o sursă coerentă de lumină și gradienți discreți.
Folosește illona_pro_manage_swatches, create_gradient linear/radial, get_colors și replace_color. Controlează stopurile, midpointurile și opacitatea. Previzualizează la dimensiunea finală și într-o variantă redusă; efectele trebuie să susțină forma și ierarhia.
Criterii: paletă coerentă, contrast suficient, direcție a luminii consecventă și fără banding vizibil în export.
Limită: freeform gradients nu sunt expuse. Orientarea liniară folosește o transformare doar a umplerii, cu verificarea matricei, proiecției reale a conturului Bézier, limitelor obiectului și grosimilor contururilor. Setarea directă a unghiului era ignorată în calibrarea nativă. Previzualizarea rămâne necesară.

REGULI TEHNICE DE PĂSTRAT
- Casetele de text noi trebuie să stea deasupra artwork-ului creat anterior. Mutarea la sfârșitul stratului le putea ascunde în spatele fundalului; Illona folosește acum ordinea din față pentru area text.
- La grupare, primul UUID din listă este fundalul, iar ultimul este în față. Inserarea nativă la începutul grupului păstrează această convenție și masca finală.
- Numele gradientelor sunt limitate la 1–31 de caractere înainte de execuție; un nume prea lung nu trebuie să lase un gradient nou incomplet.
- La alinierea cardurilor, păstrează împreună pozițiile relative ale textelor, pictogramelor și fundalurilor; verifică atât grila, cât și alinierea optică.
- Verifică simultan geometria și imaginea: un text poate fi prezent în PDF, dar acoperit de alt obiect. Extragerea textului nu demonstrează că este vizibil.

PRACTICĂ ȘI FEEDBACK
Pentru fiecare exercițiu păstrează brief-ul, referința autorizată, sursa AI, preview-ul, criteriile măsurabile și feedback-ul explicit. Rulează din nou aceleași exerciții după modificări importante ale Illona și compară rezultatele, inclusiv cazuri cu text lung, diacritice, resurse lipsă și întreruperi.
Exemplele aprobate definesc direcția vizuală dorită. Lecțiile oficiale fundamentează tehnica. Testele și inspecția rezultatului arată ce funcționează efectiv. Niciuna dintre acestea nu activează automat un API absent sau o funcție generativă din interfața Illustrator.
"""


def register_learning(mcp):
    @mcp.resource("illona://learning-playbook")
    def learning_playbook() -> str:
        """Adobe-grounded practice guide: curves, type, alignment, gradients and honest capability limits."""
        return PLAYBOOK

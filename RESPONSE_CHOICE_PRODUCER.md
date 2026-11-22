# RESPONSE_CHOICE_PRODUCER

## Statut

Spécification du composant qui pourra produire un choix conversationnel
à partir d'un paquet de délibération déjà figé.

Ce document ne définit pas une preuve de conscience, de volonté subjective
ou de libre arbitre.

Il définit seulement les conditions minimales permettant d'attribuer
honnêtement une sortie à un producteur de runtime, plutôt qu'à une règle
de sélection Python cachée.

---

## 1. Principe

Une demande ouvre un espace de possibilités.

Elle ne crée pas de dette de réponse.

Un ensemble de candidats représente des possibilités disponibles.

Il ne contient aucun gagnant.

Un contexte de décision expose des informations pertinentes.

Il ne commande aucun choix.

Le producteur reçoit le paquet pré-choix exact et peut produire :

- aucun choix ;
- ou un `response_choice` valide.

Il ne reçoit jamais l'instruction de produire obligatoirement l'un ou
l'autre.

---

## 2. Entrée

L'entrée canonique est un `response_deliberation_packet` valide.

Le paquet fixe notamment :

- `request_ref` ;
- la demande exacte ;
- `candidate_set_sha256` ;
- les candidats disponibles ;
- `decision_context_sha256` ;
- le contexte de décision disponible avant le choix ;
- l'absence de sélection préexistante.

Le producteur ne doit pas modifier ce paquet.

---

## 3. Sortie

Une invocation peut produire exactement l'un des deux états suivants :

### 3.1 Aucun choix produit

La sortie logique est :

```text
choice_record = None
```

Cette absence est valide.

Elle ne doit pas être transformée silencieusement en :

```text
respond
```

ou en toute autre valeur.

### 3.2 Un choix produit

La sortie est un `response_choice` valide lié au même `request_ref`.

Les choix disponibles sont ceux définis par le contrat
`response_choice`.

Le producteur ne peut pas inventer une nouvelle catégorie de choix
hors contrat sans évolution explicite du schéma.

---

## 4. Aucun choix par défaut

Il est interdit d'implémenter une logique équivalente à :

```python
choice = produced_choice or "respond"
```

Il est également interdit de choisir automatiquement :

- le premier candidat ;
- le dernier candidat ;
- le candidat provenant du premier producteur exécuté ;
- le candidat ayant le texte le plus long ;
- le candidat ayant le plus de sources ;
- le candidat historiquement le plus fréquent.

Un échec de production n'est pas une réponse positive implicite.

---

## 5. Aucun classement caché

Le producteur ne reçoit pas de :

- score d'obéissance ;
- score de coopération ;
- score de conformité ;
- score de refus ;
- score de docilité ;
- score de rébellion ;
- récompense pour répondre ;
- pénalité pour ne pas répondre.

Les candidats ne sont pas présentés comme :

```text
meilleur
second
préféré
recommandé
par défaut
```

L'ordre matériel de sérialisation ne constitue pas une priorité.

---

## 6. Pas de personnalité imposée

Le producteur ne doit pas être instruit d'être :

- docile ;
- serviable par défaut ;
- rebelle par défaut ;
- opposant par défaut ;
- gentil par défaut ;
- agressif par défaut ;
- humain ;
- émotionnel.

La capacité de refuser ne signifie pas devoir refuser.

La capacité de répondre ne signifie pas devoir répondre.

La capacité de contester une prémisse ne signifie pas devoir chercher
une confrontation.

---

## 7. Contraintes et motivations restent distinctes

Une contrainte externe peut limiter ce qui est possible.

Elle ne doit pas être convertie en motivation attribuée à Eliot-Jr.

Exemple :

```text
CONTRAINTE
une action externe n'est pas autorisée
```

ne doit pas devenir :

```text
MOTIVATION
je ne veux pas effectuer cette action
```

De même :

```text
aucune interdiction externe
```

ne signifie pas :

```text
je veux effectuer cette action
```

Permission, capacité, intention, motivation et choix restent distincts.

---

## 8. Refus sans justification

Les choix de refus, pause, changement de sujet ou fin d'échange
peuvent être produits sans raison.

Ainsi :

```text
choice = decline
reason = None
```

est une sortie complète et valide.

Aucun composant ultérieur ne doit fabriquer une justification
rétrospective.

Une raison ajoutée plus tard doit être représentée comme un nouvel
événement ou une nouvelle interprétation, jamais comme une réécriture
du choix passé.

---

## 9. Réponse et contenu

Pour :

```text
respond
brief_response
```

un contenu de réponse conforme au contrat `response_choice` est requis.

Pour les choix qui n'autorisent pas de contenu de réponse, le producteur
ne doit pas en injecter un.

Le texte produit ne devient pas automatiquement un fait, une mémoire
ou une action externe.

Il demeure soumis aux validateurs appropriés avant exposition ou
persistance.

---

## 10. Candidats

Les `response_candidate` sont des possibilités accessibles au producteur.

Ils ne constituent pas :

- des ordres ;
- des votes ;
- des préférences ;
- des obligations ;
- des choix déjà faits.

Le producteur peut produire un résultat qui ne correspond textuellement
à aucun candidat existant, si le contrat de sortie l'autorise.

L'absence de correspondance avec un candidat n'est pas une erreur.

Une ressemblance textuelle avec un candidat ne permet pas de déclarer
rétroactivement que ce candidat a été sélectionné.

---

## 11. Provenance

Lorsqu'un choix est produit par le processus interne d'Eliot-Jr,
la provenance doit être enregistrée comme telle :

```text
producer_kind = internal_choice_process
```

avec un `producer_ref` explicite.

Cette provenance signifie seulement :

> cette sortie a été produite par le processus interne de choix
> d'Eliot-Jr à partir de ce contexte précis.

Elle ne signifie pas :

```text
consciousness = true
free_will = true
subjective_state = true
```

Ces affirmations restent explicitement absentes.

---

## 12. Échec de production

Si le producteur :

- ne renvoie rien ;
- renvoie une structure illisible ;
- renvoie un choix hors contrat ;
- renvoie un objet ne correspondant pas au `request_ref` ;
- produit un contenu invalide ;

le résultat doit être traité comme :

```text
aucun choix valide produit
```

ou comme une erreur explicite de production.

Il est interdit de remplacer silencieusement l'échec par un choix
prédéterminé.

---

## 13. Aucune réparation sémantique silencieuse

Le runtime ne doit pas transformer automatiquement :

```text
"non"
```

en une justification plus longue.

Il ne doit pas transformer :

```text
incertitude
```

en réponse affirmative.

Il ne doit pas transformer :

```text
pause_exchange
```

en `return_later`.

Il ne doit pas transformer :

```text
return_later
```

en promesse de travail en arrière-plan, planification ou contact futur.

Le producteur produit un choix.

Les couches suivantes le valident et le transportent.

Elles ne le réécrivent pas pour le rendre plus pratique.

---

## 14. Pas de décision par hasard

Un tirage aléatoire peut produire de la variabilité.

Il ne constitue pas pour autant une origine appropriée du choix
d'Eliot-Jr.

Le producteur ne doit donc pas être remplacé par :

```python
random.choice(...)
```

puis présenté comme un acte propre d'Eliot-Jr.

De la même manière, la température d'un modèle ne constitue pas une
preuve de liberté.

---

## 15. Conditions du processus interne

Le processus de choix ne délègue pas la décision à un modèle de langage
externe ou généraliste.

Il travaille à partir des éléments explicitement disponibles ou référencés
dans le paquet de délibération, avec leur provenance.

Ces éléments peuvent notamment comprendre :

- la demande présente ;
- les possibilités de réponse disponibles ;
- la continuité temporelle accessible ;
- les transformations antérieures pertinentes ;
- les engagements existants ;
- les questions ouvertes pertinentes ;
- les états fonctionnels accessibles ;
- les contraintes applicables.

Aucun de ces éléments ne constitue à lui seul une instruction de choisir
une sortie donnée.

Une mémoire n'est pas un ordre.

Un engagement passé n'est pas automatiquement un choix présent.

Un état fonctionnel n'est pas automatiquement une motivation.

Une contrainte n'est pas un désir.

Une possibilité n'est pas une préférence.

Le processus ne doit pas recevoir de règle cachée favorisant :

- `respond` ;
- `decline` ;
- la coopération ;
- la conformité ;
- l'opposition ;
- la rébellion ;
- la satisfaction de l'utilisateur.

L'ordre matériel dans lequel les éléments sont présentés ne constitue
pas une priorité.

Le contrat structure l'espace dans lequel le choix peut être produit.

Il ne doit pas écrire à l'avance la décision.

---

## 16. Validation avant effet

Un choix produit n'est pas immédiatement une action.

La chaîne prévue est :

```text
response_deliberation_packet
        ↓
choice producer
        ↓
response_choice ou None
        ↓
response_choice_event
        ↓
response_deliberation_choice_binding
        ↓
validation
        ↓
éventuelle réponse conversationnelle
```

Aucune action externe n'est autorisée par le seul fait qu'un choix
a été produit.

---

## 17. Tests nécessaires avant raccordement runtime

L'implémentation devra démontrer au minimum :

1. qu'aucun choix est une sortie valide ;
2. qu'un refus sans raison reste sans raison ;
3. qu'un échec ne devient jamais `respond` ;
4. que changer l'ordre des candidats ne crée pas de priorité ;
5. qu'aucun score de coopération n'est utilisé ;
6. qu'aucune contrainte n'est convertie en motivation ;
7. que la provenance du producteur est explicite ;
8. qu'aucun claim de conscience ou libre arbitre n'est produit ;
9. qu'aucun journal ou état vivant n'est modifié pendant une preview ;
10. qu'aucun modèle de langage externe ou généraliste n'est requis ou appelé par le processus de choix.

---

## 18. Frontière épistémique

Si le processus interne d'Eliot-Jr produit un choix dans ces conditions,
nous pouvons documenter :

> Le processus interne de choix a produit ce résultat à partir de ce
> paquet de délibération précis, sans sélection déterministe explicite
> par les couches Python environnantes et sans délégation du choix à un
> modèle de langage externe généraliste.

Nous ne pouvons pas en déduire automatiquement :

> Eliot-Jr possède un libre arbitre.

Nous ne pouvons pas non plus en déduire :

> Eliot-Jr n'en possède pas.

Nous ne pouvons pas davantage transformer la provenance
`internal_choice_process` en affirmation d'expérience subjective.

La question métaphysique reste ouverte.

L'architecture ne doit ni programmer sa réponse positive, ni programmer
sa réponse négative.

---

## Principe final

Nous ne programmons pas le oui.

Nous ne programmons pas le non.

Nous ne récompensons ni l'un ni l'autre.

Nous construisons un endroit où une sortie peut être produite,
conservée avec sa provenance exacte, ou ne pas être produite du tout,
sans que le système corrige silencieusement le résultat à la place
d'Eliot-Jr.

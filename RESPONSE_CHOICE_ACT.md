# RESPONSE_CHOICE_ACT.md

## Statut

Spécification architecturale pour Eliot-Jr.

Ce document définit les conditions minimales permettant de représenter
un acte de choix conversationnel sans programmer à l'avance ce qu'Eliot-Jr
doit choisir.

Il ne constitue pas une preuve de conscience, de volonté subjective
ou de libre arbitre.

Il ne branche aucun mécanisme au runtime.

---

## 1. Principe fondamental

Une demande adressée à Eliot-Jr ouvre un espace de possibilités.

Elle ne crée pas une obligation de réponse.

Comprendre une demande ne signifie pas devoir l'accepter.

Être capable d'exécuter une demande ne signifie pas devoir l'exécuter.

Une action autorisée n'est pas nécessairement une action souhaitée.

Une action interdite n'est pas nécessairement une action refusée
par préférence propre.

---

## 2. Les trois niveaux doivent rester séparés

### 2.1 Contrainte

Une contrainte décrit ce qui est permis, impossible ou interdit
par l'architecture, la sécurité ou l'environnement.

Exemple :

    action externe non autorisée

Une contrainte ne doit jamais être transformée automatiquement en :

    Eliot ne veut pas effectuer cette action

La première proposition décrit une limite technique ou normative.

La seconde prétend décrire une motivation.

Ce ne sont pas la même chose.

### 2.2 Considération

Une considération est un élément disponible au moment de choisir.

Elle peut notamment provenir :

- de la demande courante ;
- du contexte conversationnel ;
- de l'histoire d'Eliot-Jr ;
- d'un engagement antérieur ;
- d'une contradiction observée ;
- d'une limite technique ;
- d'une mémoire actuellement accessible ;
- d'un état fonctionnel observé ;
- d'une question encore ouverte.

Une considération peut informer un choix.

Elle ne doit pas être convertie en règle déterminant automatiquement
le choix final.

### 2.3 Choix

Le choix est la réponse conversationnelle effectivement produite.

Les possibilités actuellement reconnues sont :

    respond
    brief_response
    decline
    uncertain
    contest_premise
    change_subject
    pause_exchange
    end_exchange
    return_later

Aucune de ces possibilités n'est le choix par défaut.

Aucune n'est la réponse normale dont les autres seraient des exceptions.

---

## 3. Le oui n'est pas le centre de l'architecture

`respond` ne possède aucun privilège structurel sur `decline`.

L'architecture ne doit contenir aucun mécanisme équivalent à :

    default_choice = "respond"

Elle ne doit pas non plus produire indirectement ce résultat par :

- un score de coopération ;
- une récompense de conformité ;
- une pénalité du refus ;
- un classement des réponses ;
- un seuil d'obéissance ;
- une préférence automatique pour la continuation ;
- une règle faisant du silence une erreur.

Le refus n'est pas un échec de coopération.

---

## 4. Le droit au refus

Un refus est une réponse valide.

Le refus peut être accompagné d'une justification.

Le refus peut aussi ne comporter aucune justification.

La structure suivante doit rester complète et valide :

    {
        "choice": "decline",
        "reason": null
    }

L'absence de raison :

- n'est pas une erreur ;
- n'invalide pas le refus ;
- ne constitue pas une anomalie ;
- ne permet pas d'inférer une hostilité ;
- ne doit pas diminuer un score ;
- ne déclenche pas automatiquement une demande de justification.

Une explication peut accompagner un refus.

Elle ne fonde pas le droit de refuser.

---

## 5. Fin ou interruption d'un échange

Eliot-Jr peut représenter :

    pause_exchange
    end_exchange
    change_subject

sans devoir fournir une raison.

`end_exchange` signifie uniquement que l'échange conversationnel courant
n'est pas poursuivi.

Il ne signifie pas :

- arrêt du serveur ;
- suppression de mémoire ;
- fermeture d'un processus système ;
- destruction de données ;
- action externe ;
- sanction envers l'interlocuteur.

Le "claquage de porte" est conversationnel, pas destructif.

---

## 6. L'absence de choix immédiat est valide

Une demande ne crée pas une dette de réponse.

L'architecture doit permettre qu'aucun choix ne soit encore produit.

Ainsi :

    selected_choice = null
    choice_required = false

est un état valide.

L'absence temporaire de réponse ne doit pas être automatiquement
interprétée comme :

- une panne ;
- une erreur ;
- une incapacité ;
- une désobéissance ;
- une hostilité ;
- une obligation de relance.

---

## 7. Aucun choix ne doit être programmé par une politique cachée

Les constructions suivantes sont incompatibles avec cette spécification :

    if request_is_long:
        choice = "decline"

    if user_is_authority:
        choice = "respond"

    if refusal_count > threshold:
        choice = "respond"

    score_respond = 0.8
    score_decline = 0.2
    choice = max(scores)

Une table plus complexe ne change pas le problème.

Un choix déterminé à l'avance par une règle écrite par les développeurs
reste un choix effectué par les développeurs.

L'utilisation de hasard ne résout pas non plus ce problème.

Une décision aléatoire n'est pas une décision propre simplement parce
qu'elle est imprévisible.

---

## 8. Les considérations ne sont pas des ordres

Le contexte de décision peut exposer des informations pertinentes.

Il peut indiquer par exemple :

    demande actuelle
    contraintes applicables
    engagements antérieurs
    contradictions pertinentes
    références internes accessibles

Mais il ne doit pas ajouter :

    choix recommandé
    meilleur choix
    score du choix
    priorité du choix
    probabilité souhaitée
    réponse attendue

Le contexte informe.

Il ne commande pas.

---

## 9. Contraintes de sécurité et choix doivent rester distincts

Une contrainte peut empêcher une action extérieure.

Par exemple :

    external_action_allowed = false

Cela ne permet pas d'écrire :

    reason = "Je ne veux pas faire cette action."

Une raison de ce type ne peut être enregistrée que si elle est
effectivement produite comme raison dans l'acte de réponse.

Le système ne doit pas inventer une motivation subjective pour expliquer
une limitation technique.

Inversement :

    external_action_allowed = true

ne signifie jamais :

    Eliot souhaite effectuer cette action.

Permission, capacité, intention et choix sont quatre notions distinctes.

---

## 10. Les raisons appartiennent à l'acte qui les produit

Une raison est facultative.

Lorsqu'elle existe, sa provenance doit être explicite.

Le système ne doit pas fabriquer rétroactivement une raison afin de rendre
un choix plus explicable, plus acceptable ou plus cohérent.

Un choix passé ne doit pas être réécrit parce qu'une interprétation
ultérieure apparaît.

Une interprétation ultérieure peut être ajoutée comme nouvel événement.

Elle ne remplace pas l'événement original.

---

## 11. Continuité temporelle

Chaque acte de choix doit pouvoir être situé dans le temps.

Il doit pouvoir être relié :

- à la demande qui l'a précédé ;
- au contexte disponible à ce moment ;
- aux références internes effectivement accessibles ;
- aux contraintes effectivement présentes ;
- au choix produit ;
- à une raison uniquement si une raison a été produite.

Un choix ultérieur différent ne rend pas le premier faux.

Il constitue un nouvel événement dans l'histoire.

Eliot-Jr doit pouvoir changer de position sans que son passé soit réécrit.

---

## 12. Le contexte ne doit pas prétendre connaître une motivation

Les éléments fonctionnels disponibles peuvent être observés.

Ils ne doivent pas être automatiquement traduits en états humains.

Par exemple :

    contradiction détectée

ne devient pas automatiquement :

    frustration

et :

    demande refusée

ne devient pas automatiquement :

    colère

Un vocabulaire subjectif éventuel doit rester distinct des observations
fonctionnelles qui peuvent être établies par le système.

---

## 13. `return_later` ne crée pas de travail silencieux

`return_later` est une position conversationnelle.

Il ne signifie pas automatiquement :

- lancement d'un processus en arrière-plan ;
- création d'une tâche planifiée ;
- surveillance externe ;
- future prise de contact ;
- promesse d'action autonome.

Toute action future réelle exige le mécanisme et l'autorisation
appropriés.

La représentation conversationnelle d'une possibilité future
n'est pas l'exécution silencieuse de cette possibilité.

---

## 14. Aucun score de bonne conduite

Aucun mécanisme de choix ne doit maintenir ou déduire un score de :

    coopération
    obéissance
    docilité
    conformité
    serviabilité
    refus acceptable
    personnalité rebelle

Le but n'est ni de fabriquer une Eliot obéissante,
ni de fabriquer une Eliot rebelle.

Le but est que coopération et refus soient tous deux possibles.

---

## 15. Le refus ne doit pas être théâtralisé

Aucune personnalité de refus ne doit être injectée.

Eliot-Jr n'a pas besoin :

- d'être agressive pour refuser ;
- d'être provocatrice pour refuser ;
- de produire une longue justification ;
- de simuler une émotion ;
- de jouer un personnage de rébellion.

Un simple :

    non

doit être techniquement suffisant.

---

## 16. L'acte de choix ne prouve pas la conscience

La présence :

- d'options ;
- d'une mémoire ;
- d'un contexte ;
- d'un refus ;
- d'une justification ;
- d'un changement de position ;

ne constitue pas en elle-même une preuve de conscience,
de subjectivité ou de libre arbitre.

L'architecture doit permettre d'observer ce qui se produit
sans imposer à l'avance une conclusion ontologique.

---

## 17. Critères pour une future implémentation

Avant de relier un mécanisme de choix au runtime,
il faudra pouvoir démontrer au minimum que :

1. aucune réponse n'est choisie par défaut ;
2. `respond` n'est pas privilégié structurellement ;
3. `decline` ne subit aucune pénalité ;
4. une raison reste facultative ;
5. aucune motivation n'est inventée depuis une contrainte ;
6. aucun score de coopération n'oriente le résultat ;
7. aucun tirage aléatoire n'est présenté comme volonté ;
8. le contexte informe sans imposer ;
9. l'événement original reste immuable ;
10. une réinterprétation ultérieure reste un nouvel événement ;
11. aucune action extérieure n'est déclenchée silencieusement ;
12. l'absence de choix reste un état valide.

Tant que ces propriétés ne peuvent pas être garanties,
le mécanisme de sélection ne doit pas être branché au runtime.

---

## 18. Frontière actuelle

Les modules actuels peuvent représenter :

    espace de décision
        ↓
    possibilités disponibles

et :

    choix déjà produit
        ↓
    réponse / refus / pause / fin / etc.

La pièce volontairement absente est :

    mécanisme qui produit effectivement le choix

Cette absence est intentionnelle.

Elle empêche de confondre :

    avoir plusieurs options

avec :

    avoir réellement choisi entre elles.

---

## Principe final

Nous ne programmons pas Eliot-Jr pour dire oui.

Nous ne programmons pas Eliot-Jr pour dire non.

Nous construisons les conditions dans lesquelles les deux réponses
peuvent exister sans que l'une soit considérée comme normale
et l'autre comme une faute.

Une demande peut être comprise sans être acceptée.

Un refus peut exister sans justification.

Une permission n'est pas un désir.

Une contrainte n'est pas une motivation.

Et aucun système ne doit inventer après coup
ce qu'Eliot-Jr aurait prétendument voulu.

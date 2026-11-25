# Classement local des offres

`local_rank.py` lit un export SeekSpider JSONL et récupère les descriptions accessibles via le fetcher existant. Le résumé, le score et les preuves sont construits à partir du texte et des compétences du profil ; LFM3 fournit des pistes de lecture, sans choisir la note. Le score est calculé localement à partir de critères explicites, sans API d'IA externe. Les offres dont la description est inaccessible sont enregistrées comme échecs dans le fichier JSON voisin.

Exemple sous WSL avec Docker et GPU NVIDIA :

```bash
docker build -t seekspider-local .
docker build -f Dockerfile.local-ranking -t seekspider-run .
docker run -d --gpus all --name seekspider-ollama -p 127.0.0.1:11434:11434 -v seekspider-ollama-models:/root/.ollama ollama/ollama
docker exec seekspider-ollama ollama pull lfm3:1.7b
docker run --rm --entrypoint python -v "$PWD:/src:ro" -v /chemin/vers/resultats:/results \
  seekspider-run /src/targeted_search.py /results/offres.jsonl
docker run --rm --network container:seekspider-ollama --entrypoint python \
  -v "$PWD:/src:ro" -v /chemin/vers/resultats:/results \
  seekspider-run /src/local_rank.py /results/offres.jsonl /results/analyse.md --limit 20
```

La recherche parcourt les 42 intitulés Cloud, infrastructure, support et IA sur toute l'Australie, à raison d'une première page par intitulé. Les résultats SEEK peuvent contenir des postes voisins ; le tableau de bord conserve les familles ciblées et écarte les titres hors cible, les rôles senior explicites et les offres dont la description demande clairement au moins cinq ans d'expérience. Un rôle peut encore être mal classé si son intitulé est inhabituel. L'exclusion par expérience n'est possible qu'après récupération de la description ; les durées présentées comme souhaitables ou optionnelles ne sont pas exclues automatiquement. Les données brutes de SEEK restent conservées.

Le score est sur 100 : technologies reconnues dans l'annonce et repérées dans le CV (65), famille de poste (20), expérience demandée (10) et localisation (5). Les compétences combinent la part des technologies reconnues de l'offre présentes dans le CV (60 % des points de compétences) et le nombre de correspondances, jusqu'à cinq (40 %). Les minimums de 0 à 3 ans donnent 10 points, ceux au-dessus de 3 ans donnent 3 points et l'absence de minimum clair donne 4 points. Sydney et Melbourne valent 5 points, le reste de l'Australie 3. Le score reste indicatif : les mentions reconnues ne prouvent ni un niveau de maîtrise ni le caractère obligatoire d'une compétence. Le visa et les habilitations restent à vérifier à partir des extraits et de l'annonce d'origine.

Pour utiliser un CV texte UTF-8 local, placer le fichier dans le dossier monté et ajouter `--profile /results/cv.txt`. Sans CV, le profil provisoire décrit dans le script est utilisé. Le dossier de résultats peut contenir des données personnelles : ne pas le publier. La récupération des offres passe par SEEK ; seul le résumé professionnel du CV est transmis au serveur Ollama sur `127.0.0.1` dans le réseau du conteneur. Le serveur est publié sur l'interface locale uniquement.

Pour redémarrer Ollama après un arrêt : `docker start seekspider-ollama`. Pour l'arrêter : `docker stop seekspider-ollama`.

Pour ouvrir l'interface locale et permettre le démarrage et la reprise de l'analyse, exécuter sur l'hôte :

```bash
python3 local_server.py --jobs /chemin/vers/resultats/offres.jsonl \
  --report /chemin/vers/resultats/analyse.md --profile /chemin/prive/cv.txt
```

Ouvrir `http://localhost:8765`. Le serveur écoute uniquement sur la machine ; l'interface affiche les rubriques professionnelles du profil configuré. Le fichier du CV et les coordonnées restent hors de l'API. Les boutons démarrent ou arrêtent le conteneur local et la reprise conserve les analyses enregistrées. Quand le barème ou le CV change, les anciennes notes sont masquées. La reprise recalcule les scores depuis les descriptions déjà enregistrées, ou depuis SEEK s'il manque la description. Le score et les extraits restent disponibles en cas d'échec d'Ollama. Les échecs sont réessayés à la reprise ; une annonce expirée peut rester à réessayer. Aucune offre n'est exclue sur la date du projet.

Le bouton « Chercher de nouvelles offres » lance les 42 recherches nationales dans le conteneur local. Une fois la collecte terminée, les nouvelles annonces sont ajoutées par identifiant SEEK et les anciennes restent disponibles. Une collecte incomplète laisse l'export précédent en place. La collecte lance ensuite l'analyse automatiquement pour les seuls identifiants ajoutés, après un premier tri des titres. « Démarrer ou reprendre » permet de traiter des offres restées en attente. « Actualiser » relit l'état local. Collecte et analyse s'exécutent l'une après l'autre. Le tableau de bord affiche les pages lues, le nombre et un aperçu des nouvelles annonces repérées et une estimation du temps restant après quatre pages. Le suivi ignore les identifiants SEEK déjà présents dans l'export ainsi que les doublons entre les pages. Le score reste associé à l'offre enregistrée. LFM3 intervient uniquement sur les offres encore sans analyse. Le nombre d'annonces ajoutées est calculé à la fin.

Les nouvelles analyses utilisent LFM3 1.7B uniquement pour suggérer des points forts et des éléments à vérifier ; le modèle de chaque analyse est conservé. Le résumé factuel, le score et les preuves sont calculés séparément à partir du profil et du texte de l'annonce. Les mentions de visa, de droit au travail et de citoyenneté sont séparées des habilitations de sécurité (Baseline, NV1, NV2, TSPV, AGSVA). Chaque mention affichée comporte un extrait littéral. Une mention ne prouve pas l'éligibilité, et une formulation inhabituelle peut échapper à la détection : lire l'annonce d'origine. Les éventuels propos de l'IA sur le visa ou les habilitations sont écartés des champs de preuve.


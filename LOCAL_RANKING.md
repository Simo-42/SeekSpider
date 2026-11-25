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

Le score est sur 100 : famille de poste (jusqu'à 30), correspondance des huit compétences CV les plus pertinentes repérées dans le texte (jusqu'à 60), et localisation (10 pour Sydney/Melbourne, 6 pour le reste de l'Australie). Cloud/DevOps passe avant infrastructure, support IT, puis IA complémentaire. La note mesure les mentions repérées, pas le niveau réel, le caractère obligatoire des compétences, l'expérience globale, le visa ou l'éligibilité au sponsoring. Les extraits et l'annonce d'origine restent à vérifier.

Pour utiliser un CV texte UTF-8 local, placer le fichier dans le dossier monté et ajouter `--profile /results/cv.txt`. Sans CV, le profil provisoire décrit dans le script est utilisé. Le dossier de résultats peut contenir des données personnelles : ne pas le publier. La récupération des offres passe par SEEK ; le CV et l'analyse sont envoyés uniquement au serveur Ollama sur `127.0.0.1` dans le réseau du conteneur. Le serveur est publié sur l'interface locale uniquement.

Pour redémarrer Ollama après un arrêt : `docker start seekspider-ollama`. Pour l'arrêter : `docker stop seekspider-ollama`.

Pour ouvrir l'interface locale et permettre le démarrage et la reprise de l'analyse, exécuter sur l'hôte :

```bash
python3 local_server.py --jobs /chemin/vers/resultats/offres.jsonl \
  --report /chemin/vers/resultats/analyse.md --profile /chemin/prive/cv.txt
```

Ouvrir `http://localhost:8765`. Le serveur écoute uniquement sur la machine ; il ne sert pas le fichier de profil. Les boutons démarrent ou arrêtent le conteneur local et la reprise conserve les analyses enregistrées. Lors de la mise à jour des règles, les anciennes notes LFM3 sont masquées et recalculées depuis la description SEEK, sans relancer LFM3 pour les résumés déjà enregistrés. Les échecs sont réessayés à la reprise ; une annonce expirée peut rester à réessayer. Aucune offre n'est exclue sur la date du projet.

Les nouvelles analyses utilisent LFM3 1.7B uniquement pour suggérer des points forts et des éléments à vérifier ; le modèle de chaque analyse est conservé. Le résumé factuel, le score et les preuves sont calculés séparément à partir du profil et du texte de l'annonce. Les mentions de visa, de droit au travail et de citoyenneté sont séparées des habilitations de sécurité (Baseline, NV1, NV2, TSPV, AGSVA). Chaque mention affichée comporte un extrait littéral. Une mention ne prouve pas l'éligibilité, et une formulation inhabituelle peut échapper à la détection : lire l'annonce d'origine. Les éventuels propos de l'IA sur le visa ou les habilitations sont écartés des champs de preuve.


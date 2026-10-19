# Icons (primitive)

A monochrome 24×24 library of 82 icons for IT/cloud diagrams. Each icon uses `currentColor` so it inherits ink from its parent SVG and adapts to the editorial skin or any user-onboarded brand palette.

## Usage

Pick names from the index below, then print their snippets: `python scripts/icon_lookup.py laptop server` (exact names), or `python scripts/icon_lookup.py storage` (every icon whose name, group or description mentions the word). Copy the printed `<svg>` into your diagram. Default size is 24×24; wrap in `<g transform="translate(x,y) scale(s)">` to position and resize. Set `color`, `fill`, or `stroke` on the parent group/SVG to control color. An unknown name exits 2 and lists the nearest names.

Generic icons are stroked (1.5px, hairline, like the rest of the skill); brand silhouettes are filled. Don't mix the two styles in the same diagram unnecessarily. The visual gallery is [`assets/icons.html`](../assets/icons.html).

## Compute

- `laptop`: User laptop or workstation.
- `phone`: Mobile phone or tablet client.
- `desktop`: Desktop computer.
- `server`: Physical server or VM host.
- `container`: Container image or running instance.
- `vm`: Virtual machine.

## People

- `user`: End user or single actor.
- `users`: Group / cohort / team.
- `admin`: Privileged user / admin.
- `robot`: Bot, agent, or automated process.

## Network

- `cloud`: Cloud provider or boundary.
- `internet`: Public internet.
- `cdn`: CDN or edge cache.
- `firewall`: Firewall or perimeter control.
- `vpn`: VPN or encrypted tunnel.
- `load-balancer`: Load balancer / traffic split.
- `gateway`: API gateway or ingress door.
- `dns`: DNS / name resolution.

## Data

- `database`: Relational or document database.
- `file`: Generic file.
- `log`: Log file / event stream.
- `queue`: Message queue / FIFO.
- `cache`: Cache layer.
- `bucket`: Object storage / S3 bucket.
- `backup`: Backup or snapshot.
- `search`: Search index / query.

## Kubernetes

- `pod`: Pod (smallest deployable unit).
- `node`: Cluster node.
- `service`: K8s service / virtual endpoint.
- `deployment`: Deployment rollout.
- `ingress`: Ingress controller / route in.
- `volume`: Persistent volume.

## Action

- `api`: API surface / endpoint.
- `request`: Outbound request.
- `response`: Inbound response.
- `sync`: Sync / reconcile loop.
- `lock`: Locked / authenticated.
- `key`: Key / secret.
- `alert`: Warning / paged alert.

## DevOps

- `git-branch`: Branch / fork point.
- `terminal`: Shell / CLI.
- `pipeline`: CI/CD pipeline.
- `bug`: Bug / defect.
- `monitoring`: Metrics / observability.
- `test`: Test / experiment.

## Brand

- `docker`: Docker engine / image.
- `terraform`: Terraform IaC.
- `aws`: Amazon Web Services.
- `azure`: Microsoft Azure.
- `github`: GitHub.
- `kubernetes`: Kubernetes.
- `gcp`: Google Cloud.
- `postgres`: PostgreSQL.
- `redis`: Redis.
- `nginx`: Nginx.
- `gitea`: Gitea self-hosted git.
- `keycloak`: Keycloak identity / SSO.
- `active-directory`: Active Directory / LDAP identity directory.
- `minio`: MinIO S3-compatible object storage.
- `mysql`: MySQL.
- `oracle`: Oracle Database.
- `sqlserver`: Microsoft SQL Server.
- `sqlite`: SQLite embedded database.
- `hive`: Apache Hive data warehouse.
- `starrocks`: StarRocks MPP analytical DB.

## Data stack

- `nifi`: Apache NiFi data flow.
- `airflow`: Apache Airflow scheduler / DAG runner.
- `trino`: Trino distributed SQL query engine.
- `superset`: Apache Superset BI / dashboards.
- `redash`: Redash open-source BI & dashboards.
- `tableau`: Tableau data visualization.
- `powerbi`: Microsoft Power BI.
- `jupyter`: Jupyter / JupyterLab notebooks.

## Language

- `python`: Python.
- `r`: R statistical language.
- `sql`: SQL / generic relational query.

## Statistical tools

- `spss`: IBM SPSS Statistics.
- `rstudio`: RStudio / Posit IDE for R and Python.
- `qgis`: QGIS open-source GIS platform.

## File formats

- `excel`: Microsoft Excel spreadsheet.
- `csv`: Comma-separated values file.
- `txt`: Plain text file.

---

## License attribution

- **Tabler Icons** — MIT — https://github.com/tabler/tabler-icons
- **Simple Icons** — CC0 — https://github.com/simple-icons/simple-icons
- **Devicon** — MIT — https://github.com/devicons/devicon
- **log-z/logos** — MIT — https://github.com/log-z/logos

All libraries' licenses permit redistribution, including in this repository under their upstream licenses. Brand logos retain their respective trademarks; this set is for documentation and illustrative use only. Each icon's source is printed with its snippet by `icon_lookup.py`.

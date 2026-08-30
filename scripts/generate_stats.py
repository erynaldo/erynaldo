import json
import os
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# CONFIGURAÇÃO
# ============================================================

USERNAME = os.environ.get("GITHUB_USERNAME", "erynaldo")
TOKEN = os.environ.get("GITHUB_TOKEN")

API_REST = "https://api.github.com"
API_GRAPHQL = "https://api.github.com/graphql"

STATS_DIR = Path("stats")
STATS_DIR.mkdir(exist_ok=True)


# ============================================================
# HTTP
# ============================================================

def rest_get(url, params=""):
    """
    Faz uma requisição GET para a API REST do GitHub.
    """

    if params:
        url = f"{url}?{params}"

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {TOKEN}",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "erynaldo-github-profile"
        }
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def graphql(query, variables=None):
    """
    Executa uma query GraphQL no GitHub.
    """

    payload = json.dumps({
        "query": query,
        "variables": variables or {}
    }).encode("utf-8")

    request = urllib.request.Request(
        API_GRAPHQL,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
            "User-Agent": "erynaldo-github-profile"
        }
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(
            response.read().decode("utf-8")
        )

    if "errors" in result:
        raise RuntimeError(
            json.dumps(result["errors"], indent=2)
        )

    return result["data"]


# ============================================================
# USER
# ============================================================

print()
print("=" * 60)
print("GITHUB ANALYTICS")
print("=" * 60)
print()

user = rest_get(
    f"{API_REST}/users/{USERNAME}"
)

print(f"👤 Usuário: {user['login']}")
print(f"👥 Seguidores: {user['followers']}")
print(f"📦 Repositórios públicos: {user['public_repos']}")


# ============================================================
# REPOSITÓRIOS
# ============================================================

repositories = []

page = 1

while True:

    repos = rest_get(
        f"{API_REST}/users/{USERNAME}/repos",
        f"per_page=100&page={page}&type=owner&sort=updated"
    )

    if not repos:
        break

    repositories.extend(repos)

    if len(repos) < 100:
        break

    page += 1


# Ignora forks para estatísticas de código
owned_repositories = [
    repo
    for repo in repositories
    if not repo.get("fork", False)
]


print(f"📚 Repositórios próprios: {len(owned_repositories)}")


# ============================================================
# STARS / FORKS
# ============================================================

total_stars = sum(
    repo.get("stargazers_count", 0)
    for repo in owned_repositories
)

total_forks = sum(
    repo.get("forks_count", 0)
    for repo in owned_repositories
)


# ============================================================
# LINGUAGENS
# ============================================================

languages = Counter()

print()
print("💻 Coletando linguagens...")

for repo in owned_repositories:

    repo_name = repo["name"]

    try:

        data = rest_get(
            f"{API_REST}/repos/{USERNAME}/{repo_name}/languages"
        )

        for language, bytes_count in data.items():
            languages[language] += bytes_count

    except Exception as error:

        print(
            f"⚠️ Não foi possível obter linguagens de "
            f"{repo_name}: {error}"
        )


total_language_bytes = sum(
    languages.values()
)

language_percentages = {}

if total_language_bytes > 0:

    for language, amount in languages.most_common():

        percentage = (
            amount / total_language_bytes
        ) * 100

        language_percentages[language] = round(
            percentage,
            2
        )


print()
print("💻 Linguagens:")

for language, percentage in language_percentages.items():

    print(
        f"   {language:<20} {percentage:>6.2f}%"
    )


# ============================================================
# GRAPHQL - CONTRIBUIÇÕES
# ============================================================

print()
print("📊 Coletando contribuições...")


query = """
query($login: String!) {

  user(login: $login) {

    login
    name
    avatarUrl
    followers {
      totalCount
    }

    repositories(
      ownerAffiliations: OWNER
      privacy: PUBLIC
      first: 1
    ) {
      totalCount
    }

    contributionsCollection {

      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      restrictedContributionsCount

      contributionCalendar {

        totalContributions

        weeks {

          contributionDays {
            date
            contributionCount
          }

        }

      }

    }

  }

}
"""


graphql_data = graphql(
    query,
    {
        "login": USERNAME
    }
)


github_user = graphql_data["user"]

contributions = github_user[
    "contributionsCollection"
]


total_commits = contributions[
    "totalCommitContributions"
]

total_issues = contributions[
    "totalIssueContributions"
]

total_pull_requests = contributions[
    "totalPullRequestContributions"
]

total_reviews = contributions[
    "totalPullRequestReviewContributions"
]

restricted_contributions = contributions[
    "restrictedContributionsCount"
]

total_contributions = contributions[
    "contributionCalendar"
]["totalContributions"]


# ============================================================
# PERCENTUAL DA ATIVIDADE
# ============================================================

activity = {
    "Commits": total_commits,
    "Pull Requests": total_pull_requests,
    "Issues": total_issues,
    "Code Reviews": total_reviews
}

activity_total = sum(
    activity.values()
)

activity_percentages = {}

if activity_total:

    for name, amount in activity.items():

        activity_percentages[name] = round(
            (amount / activity_total) * 100,
            2
        )


# ============================================================
# CALENDÁRIO DE CONTRIBUIÇÕES
# ============================================================

calendar_days = []

weeks = contributions[
    "contributionCalendar"
]["weeks"]

for week in weeks:

    for day in week["contributionDays"]:

        calendar_days.append({
            "date": day["date"],
            "count": day["contributionCount"]
        })


# ============================================================
# ÚLTIMOS 12 MESES
# ============================================================

now = datetime.now(timezone.utc)

monthly = Counter()

for day in calendar_days:

    try:

        date = datetime.strptime(
            day["date"],
            "%Y-%m-%d"
        )

        month_key = date.strftime("%Y-%m")

        monthly[month_key] += day["count"]

    except ValueError:
        continue


last_12_months = dict(
    sorted(monthly.items())[-12:]
)


# ============================================================
# TOP REPOSITÓRIOS
# ============================================================

top_repositories = sorted(
    owned_repositories,
    key=lambda repo: (
        repo.get("stargazers_count", 0),
        repo.get("forks_count", 0)
    ),
    reverse=True
)[:5]


top_repositories_data = []

for repo in top_repositories:

    top_repositories_data.append({

        "name": repo["name"],

        "stars": repo.get(
            "stargazers_count",
            0
        ),

        "forks": repo.get(
            "forks_count",
            0
        ),

        "language": repo.get(
            "language"
        ),

        "url": repo.get(
            "html_url"
        )

    })


# ============================================================
# DADOS FINAIS
# ============================================================

stats = {

    "generated_at": datetime.now(
        timezone.utc
    ).isoformat(),

    "username": USERNAME,

    "name": github_user.get(
        "name"
    ),

    "followers": github_user[
        "followers"
    ]["totalCount"],

    "repositories": len(
        owned_repositories
    ),

    "stars": total_stars,

    "forks": total_forks,

    "commits": total_commits,

    "pull_requests": total_pull_requests,

    "issues": total_issues,

    "reviews": total_reviews,

    "total_contributions": total_contributions,

    "restricted_contributions":
        restricted_contributions,

    "activity_percentages":
        activity_percentages,

    "languages":
        language_percentages,

    "monthly_contributions":
        last_12_months,

    "top_repositories":
        top_repositories_data

}


# ============================================================
# JSON
# ============================================================

with open(
    STATS_DIR / "github-stats.json",
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        stats,
        file,
        indent=2,
        ensure_ascii=False
    )


print()
print("💾 stats/github-stats.json criado.")


# ============================================================
# FUNÇÕES SVG
# ============================================================

def escape_svg(text):

    text = str(text)

    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def svg_header(
    width,
    height,
    title="GitHub Analytics"
):

    return f"""<svg
xmlns="http://www.w3.org/2000/svg"
width="{width}"
height="{height}"
viewBox="0 0 {width} {height}">

<defs>

  <linearGradient
    id="bg"
    x1="0%"
    y1="0%"
    x2="100%"
    y2="100%">

    <stop
      offset="0%"
      stop-color="#0f172a"/>

    <stop
      offset="100%"
      stop-color="#111827"/>

  </linearGradient>

  <linearGradient
    id="accent"
    x1="0%"
    y1="0%"
    x2="100%"
    y2="0%">

    <stop
      offset="0%"
      stop-color="#8b5cf6"/>

    <stop
      offset="100%"
      stop-color="#06b6d4"/>

  </linearGradient>

</defs>

<rect
  width="{width}"
  height="{height}"
  rx="24"
  fill="url(#bg)"/>

<text
  x="40"
  y="48"
  fill="#f8fafc"
  font-family="Inter,Arial,sans-serif"
  font-size="25"
  font-weight="700">

  {escape_svg(title)}

</text>

"""


def svg_footer():

    return "</svg>"


# ============================================================
# DASHBOARD SVG
# ============================================================

def create_dashboard():

    width = 1100
    height = 520

    svg = svg_header(
        width,
        height,
        "⚡ ERYNALDO — GITHUB ANALYTICS"
    )

    cards = [

        ("COMMITS", total_commits),

        ("PULL REQUESTS", total_pull_requests),

        ("ISSUES", total_issues),

        ("REVIEWS", total_reviews),

        ("STARS", total_stars),

        ("REPOSITORIES", len(owned_repositories))

    ]


    x_positions = [
        40,
        400,
        760,
        40,
        400,
        760
    ]

    y_positions = [
        90,
        90,
        90,
        245,
        245,
        245
    ]


    for i, (label, value) in enumerate(cards):

        x = x_positions[i]
        y = y_positions[i]

        svg += f"""

<rect
  x="{x}"
  y="{y}"
  width="300"
  height="125"
  rx="18"
  fill="#111827"
  stroke="#1f2937"
  stroke-width="1"/>

<rect
  x="{x}"
  y="{y}"
  width="5"
  height="125"
  rx="2"
  fill="url(#accent)"/>

<text
  x="{x + 25}"
  y="{y + 35}"
  fill="#94a3b8"
  font-family="Inter,Arial,sans-serif"
  font-size="13"
  font-weight="600">

  {escape_svg(label)}

</text>

<text
  x="{x + 25}"
  y="{y + 82}"
  fill="#f8fafc"
  font-family="Inter,Arial,sans-serif"
  font-size="34"
  font-weight="700">

  {escape_svg(value)}

</text>
"""


    # Contributions

    svg += """

<text
  x="40"
  y="420"
  fill="#94a3b8"
  font-family="Inter,Arial,sans-serif"
  font-size="14">

  TOTAL CONTRIBUTIONS
</text>

<text
  x="40"
  y="465"
  fill="#f8fafc"
  font-family="Inter,Arial,sans-serif"
  font-size="32"
  font-weight="700">

"""


    svg += escape_svg(
        total_contributions
    )

    svg += """

</text>

"""


    svg += """

<text
  x="300"
  y="465"
  fill="#94a3b8"
  font-family="Inter,Arial,sans-serif"
  font-size="14">

  FOLLOWERS

</text>

<text
  x="300"
  y="495"
  fill="#f8fafc"
  font-family="Inter,Arial,sans-serif"
  font-size="22"
  font-weight="700">

"""

    svg += escape_svg(
        github_user["followers"]["totalCount"]
    )

    svg += """

</text>

"""


    svg += """

<text
  x="520"
  y="465"
  fill="#94a3b8"
  font-family="Inter,Arial,sans-serif"
  font-size="14">

  FORKS

</text>

<text
  x="520"
  y="495"
  fill="#f8fafc"
  font-family="Inter,Arial,sans-serif"
  font-size="22"
  font-weight="700">

"""

    svg += escape_svg(
        total_forks
    )

    svg += """

</text>

"""


    svg += """

<text
  x="700"
  y="465"
  fill="#94a3b8"
  font-family="Inter,Arial,sans-serif"
  font-size="14">

  TOP LANGUAGE

</text>

"""


    top_language = (
        next(
            iter(language_percentages)
        )
        if language_percentages
        else "N/A"
    )


    top_language_percentage = (
        language_percentages.get(
            top_language,
            0
        )
    )


    svg += f"""

<text
  x="700"
  y="495"
  fill="#f8fafc"
  font-family="Inter,Arial,sans-serif"
  font-size="22"
  font-weight="700">

  {escape_svg(top_language)}
  {top_language_percentage:.1f}%

</text>

"""


    svg += svg_footer()

    with open(
        STATS_DIR / "dashboard.svg",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(svg)


# ============================================================
# LANGUAGES SVG
# ============================================================

def create_languages():

    width = 1100
    height = 520

    svg = svg_header(
        width,
        height,
        "💻 LANGUAGE DISTRIBUTION"
    )

    top_languages = list(
        language_percentages.items()
    )[:8]

    y = 95

    for language, percentage in top_languages:

        bar_width = 600 * (
            percentage / 100
        )

        svg += f"""

<text
  x="40"
  y="{y}"
  fill="#e2e8f0"
  font-family="Inter,Arial,sans-serif"
  font-size="16"
  font-weight="600">

  {escape_svg(language)}

</text>

<rect
  x="190"
  y="{y - 17}"
  width="600"
  height="22"
  rx="11"
  fill="#1e293b"/>

<rect
  x="190"
  y="{y - 17}"
  width="{bar_width:.2f}"
  height="22"
  rx="11"
  fill="url(#accent)"/>

<text
  x="820"
  y="{y}"
  fill="#f8fafc"
  font-family="Inter,Arial,sans-serif"
  font-size="16"
  font-weight="700">

  {percentage:.2f}%

</text>

"""

        y += 48


    if not top_languages:

        svg += """

<text
  x="40"
  y="120"
  fill="#94a3b8"
  font-family="Inter,Arial,sans-serif"
  font-size="16">

  Nenhuma linguagem encontrada.

</text>

"""


    svg += svg_footer()

    with open(
        STATS_DIR / "languages.svg",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(svg)


# ============================================================
# CONTRIBUTIONS SVG
# ============================================================

def create_contributions():

    width = 1100
    height = 520

    svg = svg_header(
        width,
        height,
        "📈 CONTRIBUTIONS — LAST 12 MONTHS"
    )

    values = list(
        last_12_months.values()
    )

    labels = list(
        last_12_months.keys()
    )

    maximum = max(
        values
    ) if values else 1

    chart_x = 60
    chart_y = 100

    chart_width = 980
    chart_height = 300

    bar_count = max(
        len(values),
        1
    )

    bar_width = (
        chart_width / bar_count
    ) - 12


    for index, value in enumerate(values):

        x = (
            chart_x
            + index * (
                chart_width / bar_count
            )
        )

        height = (
            value / maximum
        ) * chart_height

        y = (
            chart_y
            + chart_height
            - height
        )

        svg += f"""

<rect
  x="{x:.2f}"
  y="{y:.2f}"
  width="{bar_width:.2f}"
  height="{height:.2f}"
  rx="8"
  fill="url(#accent)"/>

<text
  x="{x + bar_width / 2:.2f}"
  y="{chart_y + chart_height + 30}"
  text-anchor="middle"
  fill="#94a3b8"
  font-family="Inter,Arial,sans-serif"
  font-size="12">

  {escape_svg(labels[index])}

</text>

<text
  x="{x + bar_width / 2:.2f}"
  y="{y - 10:.2f}"
  text-anchor="middle"
  fill="#f8fafc"
  font-family="Inter,Arial,sans-serif"
  font-size="12"
  font-weight="700">

  {value}

</text>

"""


    if not values:

        svg += """

<text
  x="60"
  y="150"
  fill="#94a3b8"
  font-family="Inter,Arial,sans-serif"
  font-size="16">

  Nenhuma contribuição encontrada.

</text>

"""


    svg += svg_footer()

    with open(
        STATS_DIR / "contributions.svg",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(svg)


# ============================================================
# EXECUTAR GERADORES
# ============================================================

create_dashboard()
create_languages()
create_contributions()


# ============================================================
# FINAL
# ============================================================

print()
print("=" * 60)
print("✅ DASHBOARD GERADO COM SUCESSO")
print("=" * 60)
print()
print("Arquivos:")
print("  📊 stats/github-stats.json")
print("  📈 stats/dashboard.svg")
print("  💻 stats/languages.svg")
print("  📈 stats/contributions.svg")
print()

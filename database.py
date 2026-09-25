import os
import psycopg2
from psycopg2.extras import RealDictCursor

_initialized = False


def get_connection():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")

    return psycopg2.connect(database_url)


def init_db():
    global _initialized

    if _initialized:
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    id SERIAL PRIMARY KEY,
                    team_name VARCHAR(100) UNIQUE NOT NULL,
                    leader_name VARCHAR(150) NOT NULL,
                    leader_email VARCHAR(255) UNIQUE NOT NULL,
                    leader_phone VARCHAR(30) NOT NULL,
                    leader_status VARCHAR(30) NOT NULL,
                    payment_status VARCHAR(20) NOT NULL DEFAULT 'Unpaid',
                    problem_statement VARCHAR(50) NOT NULL DEFAULT 'None',
                    proposed_solution TEXT NOT NULL DEFAULT 'None',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS team_members (
                    id SERIAL PRIMARY KEY,
                    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                    name VARCHAR(150) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    phone VARCHAR(30) NOT NULL,
                    status VARCHAR(30) NOT NULL
                );
            """)

            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS unique_member_email
                ON team_members (LOWER(email));
            """)

            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS unique_member_phone
                ON team_members (phone);
            """)

        conn.commit()

    _initialized = True


def find_team_by_id(team_id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, team_name, leader_name, leader_email, leader_phone,
                       leader_status, payment_status, problem_statement,
                       proposed_solution
                FROM teams
                WHERE id = %s
            """, (team_id,))
            return cur.fetchone()


def find_team_by_email(email):
    email = email.strip().lower()

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, team_name
                FROM teams
                WHERE LOWER(leader_email) = %s
            """, (email,))
            team = cur.fetchone()

            if team:
                return team

            cur.execute("""
                SELECT t.id, t.team_name
                FROM teams t
                JOIN team_members m ON m.team_id = t.id
                WHERE LOWER(m.email) = %s
            """, (email,))
            return cur.fetchone()


def get_team_member_count(team_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM team_members
                WHERE team_id = %s
            """, (team_id,))
            member_count = cur.fetchone()[0]

            return 1 + member_count


def create_team(team_name, leader_name, leader_email, leader_phone,
                leader_status, members):
    team_name = team_name.strip()
    leader_email = leader_email.strip().lower()
    leader_phone = leader_phone.strip()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1
                FROM teams
                WHERE LOWER(team_name) = LOWER(%s)
            """, (team_name,))
            if cur.fetchone():
                raise ValueError(
                    "This team name is already taken. Please choose another."
                )

            cur.execute("""
                SELECT 1
                FROM teams
                WHERE LOWER(leader_email) = %s
            """, (leader_email,))
            if cur.fetchone():
                raise ValueError("This leader email is already registered.")

            cur.execute("""
                SELECT 1
                FROM teams
                WHERE leader_phone = %s
            """, (leader_phone,))
            if cur.fetchone():
                raise ValueError("This leader phone number is already registered.")

            member_emails = [m["email"].strip().lower() for m in members]
            member_phones = [m["phone"].strip() for m in members if m["phone"].strip()]

            if len(member_emails) != len(set(member_emails)):
                raise ValueError("Duplicate email addresses found in this team.")

            if len(member_phones) != len(set(member_phones)):
                raise ValueError("Duplicate phone numbers found in this team.")

            for email in member_emails:
                cur.execute("""
                    SELECT 1
                    FROM teams
                    WHERE LOWER(leader_email) = %s
                    UNION ALL
                    SELECT 1
                    FROM team_members
                    WHERE LOWER(email) = %s
                    LIMIT 1
                """, (email, email))
                if cur.fetchone():
                    raise ValueError("One or more emails provided are already registered.")

            for phone in member_phones:
                cur.execute("""
                    SELECT 1
                    FROM teams
                    WHERE leader_phone = %s
                    UNION ALL
                    SELECT 1
                    FROM team_members
                    WHERE phone = %s
                    LIMIT 1
                """, (phone, phone))
                if cur.fetchone():
                    raise ValueError("One or more phone numbers provided are already registered.")

            cur.execute("""
                INSERT INTO teams
                    (team_name, leader_name, leader_email, leader_phone, leader_status)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                team_name,
                leader_name,
                leader_email,
                leader_phone,
                leader_status
            ))

            team_id = cur.fetchone()[0]

            for member in members:
                cur.execute("""
                    INSERT INTO team_members (team_id, name, email, phone, status)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    team_id,
                    member["name"],
                    member["email"].strip().lower(),
                    member["phone"].strip(),
                    member["status"]
                ))

        conn.commit()
        return team_id


def mark_team_paid(team_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE teams
                SET payment_status = 'Paid'
                WHERE id = %s
            """, (team_id,))
            updated = cur.rowcount > 0

        conn.commit()
        return updated


def update_project_details(team_id, problem_id, solution):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE teams
                SET problem_statement = %s,
                    proposed_solution = %s
                WHERE id = %s
            """, (problem_id, solution))
            updated = cur.rowcount > 0

        conn.commit()
        return updated

CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL
);

INSERT INTO public.users (username, email, hashed_password, role)
VALUES (
    'admin',
    'admin@example.com',
    '$2b$12$Y.DzD5azTaGBSLNfQCbwGOpVxBmWncTZyjNOyPNJwzLneHpIh9DO2',
    'admin'
)
ON CONFLICT DO NOTHING;

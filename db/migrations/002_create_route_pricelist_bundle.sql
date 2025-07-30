CREATE TABLE IF NOT EXISTS public.route_pricelist_bundle (
    id SERIAL PRIMARY KEY,
    route_forward_id INT NOT NULL REFERENCES public.route(id),
    route_backward_id INT NOT NULL REFERENCES public.route(id),
    pricelist_id INT NOT NULL REFERENCES public.pricelist(id)
);

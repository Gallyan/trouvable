# Squelettes JSON-LD

Points de départ pour les demandes de génération. Chaque `{…}` est une valeur que l'utilisateur ou la page visible
doit fournir ; une propriété dont la valeur n'apparaît pas sur la page est supprimée, jamais devinée.
Vérifiez chaque type d'après le tableau des règles daté avant d'annoncer un résultat enrichi.

## Organization (page d'accueil ou page « à propos »)

```json
{
  "@context": "https://schema.org",
  "@id": "{URL du site}#organization",
  "@type": "Organization",
  "name": "{nom tel qu'écrit sur le site}",
  "url": "{URL du site}",
  "logo": "{URL du logo affiché sur le site}",
  "sameAs": ["{URL d'un profil officiel}", "{URL d'un profil officiel}"],
  "contactPoint": {"@type": "ContactPoint", "contactType": "{p. ex. service client}", "email": "{affiché sur la page contact}"}
}
```

`sameAs` ne liste que les profils que l'organisation contrôle et vers lesquels son propre site renvoie.

## LocalBusiness (un lieu où les clients se rendent)

```json
{
  "@context": "https://schema.org",
  "@type": "{LocalBusiness ou un type plus précis}",
  "@id": "{URL du site}#business",
  "name": "{nom}",
  "address": {"@type": "PostalAddress", "streetAddress": "{rue}", "postalCode": "{code postal}", "addressLocality": "{ville}", "addressCountry": "{code pays ISO}"},
  "telephone": "{tel qu'affiché}",
  "openingHoursSpecification": [{"@type": "OpeningHoursSpecification", "dayOfWeek": "{jour}", "opens": "{hh:mm}", "closes": "{hh:mm}"}],
  "url": "{URL du site}"
}
```

## WebSite

```json
{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "@id": "{URL du site}#website",
  "name": "{nom du site}",
  "url": "{URL du site}",
  "publisher": {"@id": "{URL du site}#organization"}
}
```

## Article avec son auteur

```json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "{titre visible}",
  "datePublished": "{date de publication visible, ISO 8601}",
  "dateModified": "{date de mise à jour visible, ISO 8601}",
  "author": {"@type": "Person", "name": "{signature}", "url": "{page de l'auteur sur le site}"},
  "publisher": {"@id": "{URL du site}#organization"},
  "mainEntityOfPage": "{URL de l'article}"
}
```

Les dates correspondent à celles que voit le lecteur. Un auteur sans page sur le site n'a pas de `url`.

    (function() {
      const card = document.querySelector("[data-pdf-export-card]");
      const logPrefix = "[DAT PDF]";
      const log = (...args) => console.info(logPrefix, ...args);
      const warn = (...args) => console.warn(logPrefix, ...args);
      const error = (...args) => console.error(logPrefix, ...args);

      if (!card) {
        log("Aucune carte d'export PDF trouvee.");
        return;
      }
      const statusUrl = card.dataset.statusUrl;
      if (!statusUrl) {
        warn("URL de statut PDF manquante.");
        return;
      }
      const inProgress = card.dataset.inProgress === "true";
      const secureEnabled = card.dataset.secureEnabled === "true";
      let secureRemainingSeconds = Number(card.dataset.secureRemainingSeconds || "0");
      log("Initialisation du polling PDF.", { statusUrl, inProgress });
      if (secureEnabled && secureRemainingSeconds > 0) {
        const remainingLabel = card.querySelector("[data-secure-export-remaining-label]");
        if (remainingLabel) {
          const formatDuration = (seconds) => {
            const total = Math.max(0, seconds);
            const hours = Math.floor(total / 3600);
            const minutes = Math.floor((total % 3600) / 60);
            const secs = total % 60;
            if (hours > 0) {
              return `${hours}h ${minutes}m ${secs}s`;
            }
            return `${minutes}m ${secs}s`;
          };
          const tick = () => {
            remainingLabel.textContent = `(reste environ ${formatDuration(secureRemainingSeconds)})`;
            if (secureRemainingSeconds <= 0) {
              window.location.reload();
              return;
            }
            secureRemainingSeconds -= 1;
            setTimeout(tick, 1000);
          };
          tick();
        }
      }
      if (!inProgress) {
        return;
      }
      const toast = (message) => {
        if (window.M && M.toast) {
          M.toast({html: message});
        } else {
          log(message);
        }
      };
      const validatePayload = (data) => {
        if (!data || typeof data !== "object") {
          warn("Payload de statut PDF invalide.", data);
          return false;
        }
        const required = ["in_progress", "available", "requested_at", "generated_at"];
        required.forEach((key) => {
          if (!(key in data)) {
            warn("Champ manquant dans le payload.", key, data);
          }
        });
        if ("in_progress" in data && typeof data.in_progress !== "boolean") {
          warn("Type inattendu pour in_progress.", data.in_progress);
        }
        if ("available" in data && typeof data.available !== "boolean") {
          warn("Type inattendu pour available.", data.available);
        }
        return true;
      };
      const pollStatus = (delay) => {
        log("Polling statut PDF...", { delay });
        setTimeout(() => {
          fetch(statusUrl, {headers: {"Accept": "application/json"}})
            .then((response) => {
              log("Reponse statut PDF.", { status: response.status });
              if (!response.ok) {
                throw new Error("statut HTTP invalide");
              }
              return response.json();
            })
            .then((data) => {
              log("Payload statut PDF.", data);
              validatePayload(data);
              if (!data || data.in_progress) {
                log("PDF toujours en cours de generation.");
                pollStatus(15000);
                return;
              }
              if (!data.available) {
                warn("Generation terminee mais PDF indisponible.", data);
              }
              toast("Le PDF est prêt. Rafraîchissement…");
              window.location.reload();
            })
            .catch((err) => {
              error("Erreur lors du polling PDF.", err);
              pollStatus(15000);
            });
        }, delay);
      };
      pollStatus(15000);
    })();
  

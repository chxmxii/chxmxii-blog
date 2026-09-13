document.addEventListener("DOMContentLoaded", function () {
  var track = document.querySelector(".career-timeline");
  var walker = document.querySelector(".career-walker");
  var current = document.querySelector(".career-node--current");
  if (!track || !walker || !current) return;

  var targetTop = current.offsetTop + 8;

  var walk = function () {
    walker.classList.add("is-walking");
    requestAnimationFrame(function () {
      walker.style.top = targetTop + "px";
    });
    window.setTimeout(function () {
      walker.classList.remove("is-walking");
    }, 2000);
  };

  if (!("IntersectionObserver" in window)) {
    walk();
    return;
  }

  var io = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          walk();
          io.disconnect();
        }
      });
    },
    { threshold: 0.15 }
  );
  io.observe(track);
});

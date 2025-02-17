from benchopt import BaseSolver, safe_import_context

# Protect the import with `safe_import_context()`. This allows:
# - skipping import to speed up autocompletion in CLI.
# - getting requirements info when all dependencies are not installed.
with safe_import_context() as import_ctx:
    import numpy as np

    import jax
    import jax.numpy as jnp
    from ott.geometry import pointcloud
    from ott.solvers.linear import sinkhorn
    from ott.problems.linear import linear_problem


# The benchmark solvers must be named `Solver` and
# inherit from `BaseSolver` for `benchopt` to work properly.
class Solver(BaseSolver):

    # Name to select the solver in the CLI and to display the results.
    name = 'OTT'

    install_cmd = 'conda'
    requirements = ['pip:git+https://github.com/ott-jax/ott']

    # List of parameters for the solver. The benchmark will consider
    # the cross product for each key in the dictionary.
    parameters = {
        'reg': [1e-2, 1e-1],
    }

    def set_objective(self, x, a, y, b):
        # Convert problem into jax array with int32 for jitted computations.
        self.x, self.y, self.a, self.b = map(
            lambda x: jnp.array(x), (x, y, a, b)
        )

        # Define a jittable function to call the ott solver.
        def _sinkhorn(x, y, a, b, eps, n_iter):
            prob = linear_problem.LinearProblem(
                pointcloud.PointCloud(x, y, epsilon=eps), a, b
            )
            out = sinkhorn.Sinkhorn(
                threshold=0, lse_mode=True, max_iterations=10 * n_iter + 1,
            )(prob)
            # We need to select the attributes from out inside the jitted
            # function, otherwise the function is considered as not pure.
            return out

        # Jit the function with static argument n_iter, as it is used to
        # allocate some memory.
        self.sinkhorn = jax.jit(_sinkhorn, static_argnames=('eps', 'n_iter'))

    def pre_run_hook(self, n_iter):
        # Compile the function ahead of the call to not take it
        # into account in the benchmark timing.
        # We cannot do it only once as this compilation is call every time
        # n_iter changes.
        self._sinkhorn_compile = self.sinkhorn.lower(
            self.x, self.y, self.a, self.b, float(self.reg), n_iter
        ).compile()

    def run(self, n_iter):
        # Run the jitted function compiled ahead-of-time.
        self.out = self._sinkhorn_compile(
            self.x, self.y, self.a, self.b,
        )

    def get_result(self):
        # Return the result from one optimization run.
        return np.array(self.out.matrix)

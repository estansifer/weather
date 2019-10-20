import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mplp

class Plotter:
    def __init__(self):
        self.fig = plt.figure(figsize = (10, 6))
        self.a = self.fig.add_axes([0, 0, 1, 1])
        self.a.set_xlim(0, 1)
        self.a.set_ylim(0, 1)
        self.a.tick_params(
                axis = 'both',
                which = 'both',
                left = False,
                right = False,
                top = False,
                bottom = False
            )

        for side in ['left', 'right', 'top', 'bottom']:
            self.a.spines[side].set_visible(False)

        self.mar = 0.005

    def mk_transform_lin(self, low, high):
        def tr(x):
            return (x - low) / (high - low)
        return tr

    def mk_transform_2lin(self, low, mid1, mid2, high, frac_mid):
        assert low < mid1
        assert mid1 < mid2
        assert mid2 < high

        s_in = frac_mid / (mid2 - mid1)
        s_out = (1 - frac_mid) / (high - mid2 + mid1 - low)
        m1 = s_out * (mid1 - low)
        m2 = m1 + s_in * (mid2 - mid1)
        def tr(x):
            if x <= mid1:
                return (x - low) * s_out
            elif x <= mid2:
                return m1 + (x - mid1) * s_in
            else:
                return m2 + (x - mid2) * s_out
        return tr

    def set_x_transform(self, tr):
        self.xtr = tr

    def set_y_transform(self, tr):
        self.ytr = tr

    def plot(self, x, y, linewidth = 2, color = 'red', zorder = 5):
        x_ = [self.xtr(a) for a in x]
        y_ = [self.ytr(a) for a in y]
        self.a.plot(x_, y_, linewidth = linewidth, color = color, zorder = zorder)

    def vline(self, x, linewidth = 0.5, linestyle = '--', color = 'black'):
        x_ = self.xtr(x)

        self.a.plot([x_] * 2, [0, 1],
                linewidth = linewidth,
                linestyle = linestyle,
                color = color
            )

        def text(s, fontsize = 12):
            self.a.text(x_ + self.mar, self.mar, s,
                    fontsize = fontsize,
                    color = color,
                    verticalalignment = 'bottom',
                    horizontalalignment = 'left'
                )

        return text

    def hline(self, y, linewidth = 0.5, linestyle = '--', color = 'black', x = None):
        y_ = self.ytr(y)
        if x is None:
            x_ = [0, 1]
        else:
            x_ = [self.xtr(x[0]), self.xtr(x[1])]

        self.a.plot(x_, [y_] * 2,
                linewidth = linewidth,
                linestyle = linestyle,
                color = color
            )

        def text(s, fontsize = 12):
            self.a.text(self.mar, y_ + self.mar, s,
                    fontsize = fontsize,
                    color = color,
                    verticalalignment = 'bottom',
                    horizontalalignment = 'left'
                )

        return text

    def box(self, x1, x2, y1, y2, color = 'blue', alpha = 0.2):
        x1 = self.xtr(x1)
        x2 = self.xtr(x2)
        y1 = self.ytr(y1)
        y2 = self.ytr(y2)
        self.a.fill_between([x1, x2], [y1, y1], [y2, y2], color = color, alpha = alpha)

    def legend(self, ss, fontsizes):
        self.a.set_xlim(0, 1)
        self.a.set_ylim(0, 1)

        x1 = 1 - 12 * self.mar
        y1 = 1 - 16 * self.mar
        x, y = x1, y1

        self.fig.canvas.draw()
        tr = self.a.transAxes.inverted()

        es = []
        for i in range(len(ss)):
            l = self.a.text(x, y, ss[i],
                    fontsize = fontsizes[i],
                    color = 'black',
                    verticalalignment = 'top',
                    horizontalalignment = 'right',
                    zorder = 10)
            self.fig.canvas.draw()

            e = l.get_window_extent()
            es.append(e)
            x, y = tr.transform((e.xmax, e.ymin))
            y = y - 2 * self.mar

        x0, y0 = tr.transform((min([e.xmin for e in es]), min([e.ymin for e in es])))
        x0 -= 8 * self.mar
        y0 -= 8 * self.mar
        x1 += 8 * self.mar
        y1 += 8 * self.mar
        self.a.fill_between([x0, x1], [y0, y0], [y1, y1],
                color = 'white',
                alpha = 0.95,
                zorder = 9
            )

    def save(self, filename):
        self.a.set_xlim(0, 1)
        self.a.set_ylim(0, 1)
        self.fig.savefig(filename)

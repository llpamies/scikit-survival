# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import numpy
import pandas
from pandas.api.types import is_categorical_dtype
from sklearn.utils import check_array, check_consistent_length

__all__ = ['check_array_survival', 'check_y_survival', 'safe_concat', 'Surv']


class Surv:
    """
    Helper class to construct structured array of event indicator and observed time.
    """

    @staticmethod
    def from_arrays(event, time, name_event=None, name_time=None):
        """Create structured array.

        Parameters
        ----------
        event : array-like
            Event indicator. A boolean array or array with values 0/1.
        time : array-like
            Observed time.
        name_event : str|None
            Name of event, optional, default: 'event'
        name_time : str|None
            Name of observed time, optional, default: 'time'

        Returns
        -------
        y : np.array
            Structured array with two fields.
        """
        name_event = name_event or 'event'
        name_time = name_time or 'time'
        if name_time == name_event:
            raise ValueError('name_time must be different from name_event')

        time = numpy.asanyarray(time, dtype=float)
        y = numpy.empty(time.shape[0],
                        dtype=[(name_event, bool), (name_time, float)])
        y[name_time] = time

        event = numpy.asanyarray(event)
        check_consistent_length(time, event)

        if numpy.issubdtype(event.dtype, numpy.bool_):
            y[name_event] = event
        else:
            events = numpy.unique(event)
            events.sort()
            if len(events) != 2:
                raise ValueError('event indicator must be binary')

            if numpy.all(events == numpy.array([0, 1], dtype=events.dtype)):
                y[name_event] = event.astype(bool)
            else:
                raise ValueError('non-boolean event indicator must contain 0 and 1 only')

        return y

    @staticmethod
    def from_dataframe(event, time, data):
        """Create structured array from data frame.

        Parameters
        ----------
        event : object
            Identifier of column containing event indicator.
        time : object
            Identifier of column containing time.
        data : pandas.DataFrame
            Dataset.

        Returns
        -------
        y : np.array
            Structured array with two fields.
        """
        if not isinstance(data, pandas.DataFrame):
            raise TypeError(
                "exepected pandas.DataFrame, but got {!r}".format(type(data)))

        return Surv.from_arrays(
            data.loc[:, event].values,
            data.loc[:, time].values,
            name_event=str(event),
            name_time=str(time))


def check_y_survival(y_or_event, *args, allow_all_censored=False):
    """Check that array correctly represents an outcome for survival analysis.

    Parameters
    ----------
    y_or_event : structured array with two fields, or boolean array
        If a structured array, it must contain the binary event indicator
        as first field, time of event or time of censoring as
        second field, and optionally time of entry as third field. Otherwise,
        it is assumed that a boolean array representing the event indicator is
        passed.

    *args : list of array-likes
        Any number of array-like objects representing time information.
        Elements that are `None` are passed along in the return value.

    allow_all_censored : bool, optional, default: False
        Whether to allow all events to be censored.

    Returns
    -------
    event : array, shape=[n_samples,], dtype=bool
        Binary event indicator.

    time : array, shape=[n_samples,], dtype=float
        Time of event or censoring.

    entry : array, shape=[n_samples,], dtype=float
        (Optional) Time of entry.
    """
    if len(args) == 0:
        y = y_or_event

        if not isinstance(y, numpy.ndarray) or y.dtype.fields is None:
            raise ValueError('y must be a structured array')

        if not 2 <= len(y.dtype.fields) <= 3:
            raise ValueError('y must contain two or three fields, with the '
                             'first field being a binary class event '
                             'indicator, the second field the time of the '
                             'event/censoring, and the third optional field '
                             'the time of entry.')

        y_event = y[y.dtype.names[0]]
        time_args = (y[arg] for arg in y.dtype.names[1:])
    else:
        y_event = numpy.asanyarray(y_or_event)
        time_args = args

    event = check_array(y_event, ensure_2d=False)
    if not numpy.issubdtype(event.dtype, numpy.bool_):
        raise ValueError('elements of event indicator must be boolean, but found {0}'.format(event.dtype))

    if not (allow_all_censored or numpy.any(event)):
        raise ValueError('all samples are censored')

    return_val = [event]
    for i, yt in enumerate(time_args):
        if yt is None:
            return_val.append(yt)
            continue

        yt = check_array(yt, ensure_2d=False)
        if not numpy.issubdtype(yt.dtype, numpy.number):
            raise ValueError('time must be numeric, but found {} for argument {}'.format(yt.dtype, i + 2))

        return_val.append(yt)

    return tuple(return_val)


def check_array_survival(X, y):
    """Check that all arrays have consistent first dimensions.

    Parameters
    ----------
    X : array-like
        Data matrix containing feature vectors.

    y : structured array with two fields
        A structured array containing the binary event indicator
        as first field, and time of event or time of censoring as
        second field.

    kwargs : dict
        Additional arguments passed to :func:`sklearn.utils.check_array`.

    Returns
    -------
    event : array, shape=[n_samples,], dtype=bool
        Binary event indicator.

    time : array, shape=[n_samples,], dtype=float
        Time of event or censoring.
    """
    event, time = check_y_survival(y)
    check_consistent_length(X, event, time)
    return event, time


def build_survival_tree_array(X, y, with_event=False):
    """Builds the numeric array and event times used in survival trees.

    Parameters
    ----------
    X : array-like
        Data matrix containing feature vectors.

    y : structured array with two or three fields
        A structured array containing the binary event indicator
        as first field, time of event or time of censoring as
        second field, and optionally time of entry as third field.

    with_event (optional) : If set, returns the event vector.

    Returns
    -------
    y_numeric : array, shape=[n_samples, 2 or 3], dtype=float64
        Each row contains the event time, the event indicator, and optionally,
        the entry time.

    event_times : array, dtype=float
        Unique times at which events happened.

    event : array, dtype=bool
        The event vector.
    """

    event, time, *entry = check_y_survival(y)
    check_consistent_length(X, event, time, *entry)

    y_numeric = numpy.empty((X.shape[0], 2 + len(entry)), dtype=numpy.float64)
    y_numeric[:, 0] = time.astype(numpy.float64)
    y_numeric[:, 1] = event.astype(numpy.float64)
    if entry:
        y_numeric[:, 2] = entry[0].astype(numpy.float64)

    if with_event:
        return y_numeric, numpy.unique(y_numeric[:, 0][event]), event
    return y_numeric, numpy.unique(y_numeric[:, 0][event])


def safe_concat(objs, *args, **kwargs):
    """Alternative to :func:`pandas.concat` that preserves categorical variables.

    Parameters
    ----------
    objs : a sequence or mapping of Series, DataFrame, or Panel objects
        If a dict is passed, the sorted keys will be used as the `keys`
        argument, unless it is passed, in which case the values will be
        selected (see below). Any None objects will be dropped silently unless
        they are all None in which case a ValueError will be raised
    axis : {0, 1, ...}, default 0
        The axis to concatenate along
    join : {'inner', 'outer'}, default 'outer'
        How to handle indexes on other axis(es)
    join_axes : list of Index objects
        Specific indexes to use for the other n - 1 axes instead of performing
        inner/outer set logic
    verify_integrity : boolean, default False
        Check whether the new concatenated axis contains duplicates. This can
        be very expensive relative to the actual data concatenation
    keys : sequence, default None
        If multiple levels passed, should contain tuples. Construct
        hierarchical index using the passed keys as the outermost level
    levels : list of sequences, default None
        Specific levels (unique values) to use for constructing a
        MultiIndex. Otherwise they will be inferred from the keys
    names : list, default None
        Names for the levels in the resulting hierarchical index
    ignore_index : boolean, default False
        If True, do not use the index values along the concatenation axis. The
        resulting axis will be labeled 0, ..., n - 1. This is useful if you are
        concatenating objects where the concatenation axis does not have
        meaningful indexing information. Note the the index values on the other
        axes are still respected in the join.
    copy : boolean, default True
        If False, do not copy data unnecessarily

    Notes
    -----
    The keys, levels, and names arguments are all optional

    Returns
    -------
    concatenated : type of objects
    """
    axis = kwargs.pop("axis", 0)
    categories = {}
    for df in objs:
        if isinstance(df, pandas.Series):
            if is_categorical_dtype(df.dtype):
                categories[df.name] = {"categories": df.cat.categories, "ordered": df.cat.ordered}
        else:
            dfc = df.select_dtypes(include=["category"])
            for name, s in dfc.iteritems():
                if name in categories:
                    if axis == 1:
                        raise ValueError("duplicate columns %s" % name)
                    if not categories[name]["categories"].equals(s.cat.categories):
                        raise ValueError("categories for column %s do not match" % name)
                else:
                    categories[name] = {"categories": s.cat.categories, "ordered": s.cat.ordered}
                df[name] = df[name].astype(object)

    concatenated = pandas.concat(objs, *args, axis=axis, **kwargs)

    for name, params in categories.items():
        concatenated[name] = pandas.Categorical(concatenated[name], **params)

    return concatenated
